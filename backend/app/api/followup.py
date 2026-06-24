from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
import logging
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.utils.file_validation import validate_file
from app.models.followup import Followup
from app.models.guardian import Guardian
from app.utils.followup_policy import is_followup_limited

router = APIRouter(prefix="/followup", tags=["followup"])
logger = logging.getLogger(__name__)

# NOTE: 경과 보고의 AI 처리는 v2 followup_filter 에이전트가 담당한다.
# create_followup은 followup_filter를 호출해 분류·누적요약·이미지저장·자연스러운 응답을
# 만들고(매 메시지 응답), 저장/조회/업로드 + 수의사 알람을 담당한다.
# (옛 ai/agents/followup.py · run_followup_sync는 제거됨)


class FollowupCreate(BaseModel):
    emrid: int
    images: List[str]
    message: Optional[str] = None


def _is_recent_emergency(emergency_alert, created_at, *, now=None, window_hours: int = 24) -> bool:
    """직전 경과가 '최근(기본 24h) + 응급'인지 판정(순수 함수, 테스트 용이).

    오래된 응급 경과가 나중의 일반 예약 변경에까지 영향 주는 것을 막기 위해 시간창으로 제한한다.
    """
    if not emergency_alert or created_at is None:
        return False
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    ca = created_at
    if getattr(ca, "tzinfo", None) is None:
        ca = ca.replace(tzinfo=timezone.utc)
    return (now - ca) <= timedelta(hours=window_hours)


def _apply_urgent_slot_priority(recs: dict, urgent: bool) -> dict:
    """긴급 경과면 '가장 빠른 슬롯(earliest)'을 기본 추천(recommended)으로 끌어올린다.

    recommend_slots는 시작일 offset이 아니라 day-quota만 바꾸므로, 가장 빠른 슬롯을 확실히
    우선 노출하려면 프론트가 먼저 보여주는 recommended 자리에 earliest를 싣는다(프론트 무변경).
    자동 확정은 하지 않는다 — 추천 순서만 바꾼다.
    """
    if not urgent:
        return recs
    earliest = recs.get("earliest") or []
    if not earliest:
        return recs
    return {**recs, "recommended": earliest, "urgent": True}


async def _build_rebook_slots(db: AsyncSession, emrid: int, schedule) -> Optional[dict]:
    """재예약용 슬롯 추천 — 기존 예약의 의사/병원 + 이전 문진 기준으로 슬롯을 다시 계산.

    프론트가 이 슬롯을 그대로 렌더해 '원래 예약과 동일한 구조'로 시간을 고르게 한다.
    세션 ref 상태와 무관하게 emrid만으로 동작. 데이터가 없거나 실패하면 None.
    """
    if not schedule:
        return None
    from datetime import date as date_type

    from app.models.doctor import Doctor
    from app.models.pet import Pet
    from app.models.triage_result import TriageResult

    triage = (await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))).scalar_one_or_none()
    guardian = (await db.execute(select(Guardian).where(Guardian.emrid == emrid))).scalar_one_or_none()
    pet = (await db.execute(select(Pet).where(Pet.petid == guardian.petid))).scalar_one_or_none() if guardian else None
    if not pet:
        return None

    doctor = (await db.execute(select(Doctor).where(Doctor.doctorid == schedule.doctorid))).scalar_one_or_none()
    hospitalid = doctor.hospitalid if doctor else None

    # 직전 followup 1건이 최근 24h 이내 응급 경과면, 원래 triage 응급도보다 이를 우선 반영한다.
    # (booked 상태에서 발작·혈토·요폐·호흡곤란 등으로 emergency_alert=True 저장된 경우)
    latest_fu = (await db.execute(
        select(Followup).where(Followup.emrid == emrid).order_by(Followup.created_at.desc()).limit(1)
    )).scalars().first()
    urgent_followup = bool(latest_fu) and _is_recent_emergency(
        getattr(latest_fu, "emergency_alert", None), getattr(latest_fu, "created_at", None)
    )

    age = (date_type.today().year - pet.birth_date.year) if pet.birth_date else None
    pet_payload = {
        "name": pet.petname, "species": pet.species or "dog", "breed": pet.breed or "알 수 없음",
        "age": age, "gender": pet.gender, "weight": float(pet.weight_kg) if pet.weight_kg else None,
    }
    # 긴급 경과면 보수적으로 '가장 빠른' 기준(RED)으로 슬롯을 추천한다.
    # 그 외엔 문진 응급도, 문진 없으면(검진예약 등) 일반(GREEN) 기준.
    triage_info = {
        "urgency": "RED" if urgent_followup else (triage.urgency_level if triage else "GREEN"),
        "urgency_level_num": 1 if urgent_followup else (triage.urgency_level_num if triage else 5),
        "chief_complaint": triage.chief_complaint if triage else None,
        "suspected_diseases": (triage.suspected_diseases or []) if triage else [],
        "symptom_summary": triage.symptom_summary if triage else None,
    }
    try:
        from ai.graph import run_schedule_pipeline
        # 재예약도 첫 예약처럼 '병원 전체' 기준으로 추천 → 수의사별(by_doctor)이 채워져
        # 슬롯 카드에 의사 이름이 뜨고, 다른 의사로도 바꿀 수 있다. (한 의사로 잠그지 않음)
        recs = await run_schedule_pipeline(
            pet=pet_payload, triage=triage_info,
            hospitalid=hospitalid, doctorid=None,
        )
    except Exception as e:
        logger.warning(f"[Followup] 재예약 슬롯 계산 실패 emrid={emrid}: {e}")
        return None
    # 긴급이면 가장 빠른 슬롯을 기본 추천 자리로 끌어올린다(자동 확정 아님 — 노출 순서만).
    recs = _apply_urgent_slot_priority(recs, urgent_followup)
    return {"schedule_id": schedule.scheduleid, **recs}


async def _list_upcoming_schedules(db: AsyncSession, userid: int, petid: int, limit: int = 3) -> list[dict]:
    """챗 안에서 보여줄 '다가오는 확정 예약' 요약 목록(최대 limit건).

    예약내역 페이지(get_schedules_by_userid)와 같은 소스/필터('upcoming')를 써서 일관되게 보여준다.
    """
    from app.crud.schedule import get_schedules_by_userid
    from app.utils.timezone import to_kst

    try:
        rows, _ = await get_schedules_by_userid(
            db, userid=userid, page=1, size=limit, filter="upcoming", pet_id=petid
        )
    except Exception as e:
        logger.warning(f"[Followup] 예약 목록 조회 실패 userid={userid}: {e}")
        return []

    out: list[dict] = []
    for row in rows:
        sched, pet, doctor, _category, hospital = row
        when = None
        if sched.confirmed_time:
            try:
                k = to_kst(sched.confirmed_time)
                when = f"{k.month}월 {k.day}일 {k.hour:02d}:{k.minute:02d}"
            except Exception:
                when = str(sched.confirmed_time)
        out.append({
            "schedule_id": sched.scheduleid,
            "when": when,
            "pet_name": getattr(pet, "petname", None),
            "doctor_name": getattr(doctor, "doctor_name", None) if doctor else None,
            "hospital_name": getattr(hospital, "hospital_name", None) if hospital else None,
            "status": sched.status,
        })
    return out


async def _list_current_schedule(db: AsyncSession, emrid: int) -> list[dict]:
    """현재 emrid에 매핑된 확정 예약 1건만 요약 형태로 반환."""
    from app.models.schedule import Schedule
    from app.models.pet import Pet
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital
    from app.models.guardian import Guardian
    from app.utils.timezone import to_kst

    try:
        stmt = (
            select(Schedule, Pet, Doctor, Hospital)
            .join(Guardian, Guardian.emrid == Schedule.emrid)
            .join(Pet, Pet.petid == Guardian.petid)
            .outerjoin(Doctor, Doctor.doctorid == Schedule.doctorid)
            .outerjoin(Hospital, Hospital.hospitalid == Doctor.hospitalid)
            .where(Schedule.emrid == emrid, Schedule.deleted_at.is_(None))
        )
        row = (await db.execute(stmt)).first()
    except Exception as e:
        logger.warning(f"[Followup] 현재 예약 단건 조회 실패 emrid={emrid}: {e}")
        return []

    if not row:
        return []

    sched, pet, doctor, hospital = row
    when = None
    if sched.confirmed_time:
        try:
            k = to_kst(sched.confirmed_time)
            when = f"{k.month}월 {k.day}일 {k.hour:02d}:{k.minute:02d}"
        except Exception:
            when = str(sched.confirmed_time)
    
    return [{
        "schedule_id": sched.scheduleid,
        "when": when,
        "pet_name": getattr(pet, "petname", None),
        "doctor_name": getattr(doctor, "doctor_name", None) if doctor else None,
        "hospital_name": getattr(hospital, "hospital_name", None) if hospital else None,
        "status": sched.status,
    }]


def _last_prep_instructions(chat_session) -> list[str]:
    """대화 기록에서 마지막으로 저장된 '내원 전 준비사항' 카드(items)를 찾아 돌려준다."""
    for m in reversed((chat_session.messages if chat_session else None) or []):
        card = (m or {}).get("meta", {}).get("card") if isinstance(m, dict) else None
        if isinstance(card, dict) and card.get("kind") == "instructions":
            items = card.get("items")
            if isinstance(items, list) and items:
                return [str(x) for x in items]
    return []


# 경과사진 등록
@router.post("", status_code=201)
async def create_followup(
    request: FollowupCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await db.execute(select(Guardian).where(Guardian.emrid == request.emrid))
    guardian = result.scalar_one_or_none()
    if not guardian:
        raise HTTPException(status_code=404, detail="문진 정보를 찾을 수 없습니다.")

    # 소유권 검증: 본인 반려동물의 문진에만 경과 등록 가능
    from app.crud.schedule import get_emrid_owner_userid
    owner_id = await get_emrid_owner_userid(db, request.emrid)
    if owner_id != current_user.userid:
        raise HTTPException(status_code=403, detail="경과 등록 권한이 없습니다.")

    # 예약 정보 조회 — 시간 가드 + 수의사 알람에 사용
    from datetime import datetime, timezone
    from app.models.schedule import Schedule
    sched_row = await db.execute(
        select(Schedule).where(Schedule.emrid == request.emrid, Schedule.deleted_at.is_(None))
    )
    schedule = sched_row.scalar_one_or_none()

    followup_limited = False
    if schedule and schedule.confirmed_time:
        confirmed = schedule.confirmed_time
        if confirmed.tzinfo is None:
            confirmed = confirmed.replace(tzinfo=timezone.utc)
        followup_limited = is_followup_limited(confirmed, now=datetime.now(timezone.utc))

    # ── 경과 메시지도 메인 챗과 동일하게 오케스트레이터 라우터를 거친다.
    #    예약 후(BOOKED)엔 LLM이 reception ⇄ followup_filter 를 판단:
    #      "토한다"→경과 저장 / "병원 언제까지해?"→reception(MCP)으로 진짜 안내.
    #    (옛날엔 followup_filter 직행 → 병원 질문에 캔드 멘트만 나가던 버그)
    from ai.orchestrator.graph import run_turn
    from ai.orchestrator.state import build_context

    # 재진입 복원 + 라우팅 맥락(history)·hospitalid 확보를 위해 chat 세션을 먼저 로드.
    from app.models.chat_history import ChatHistory
    chat_row = await db.execute(
        select(ChatHistory).where(
            ChatHistory.emrid == request.emrid,
            ChatHistory.is_deleted == False,  # noqa: E712
        )
    )
    chat_session = chat_row.scalar_one_or_none()

    if followup_limited and chat_session is not None and schedule and schedule.status != "CANCELLED":
        try:
            from app.api.chat import _ensure_followup_limit_notice
            await _ensure_followup_limit_notice(db, chat_session, schedule)
        except Exception as e:
            logger.warning(f"[Followup] 10분 전 공지 저장 실패 emrid={request.emrid}: {e}")

    # 직전 누적 경과 메모(같은 emrid의 마지막 followup ai_summary)를 이어붙임 기준으로 전달.
    prior_row = await db.execute(
        select(Followup)
        .where(Followup.emrid == request.emrid)
        .order_by(Followup.created_at.desc())
    )
    prior = prior_row.scalars().first()

    if chat_session is not None:
        # build_context: phase(BOOKED) 계산 + hospitalid·pet_info·history 채움.
        ctx = await build_context(db, chat_session, request.message or "", request.images or [])
        # 경과 누적요약은 followupDB 기준(orch_state보다 우선)으로 맞춘다.
        ctx.followup_summary = (prior.ai_summary if prior else "") or ""
        ctx.followup_limited = followup_limited
    else:
        # 챗 세션이 없으면(드문 경우) 최소 ctx로 구성.
        from ai.orchestrator.contracts import Flow, Phase, SessionContext
        from ai.orchestrator.state import _primary_hospitalid, _pet_info
        ctx = SessionContext(
            session_id=0,
            userid=current_user.userid,
            petid=guardian.petid,
            pet_info=await _pet_info(db, guardian.petid),
            hospitalid=await _primary_hospitalid(db, current_user.userid),
            emrid=request.emrid,
            scheduleid=getattr(schedule, "scheduleid", None),
            user_message=request.message or "",
            attachments=request.images or [],
            phase=Phase.BOOKED,
            active_flow=Flow.IDLE,
            followup_summary=(prior.ai_summary if prior else "") or "",
            followup_limited=followup_limited,
            db=db,
        )

    agent_result = await run_turn(ctx)
    # followup_saved 이벤트에서 응급 여부를 함께 읽는다(응급 경과는 알림을 구분하기 위함).
    saved_ev = next((ev for ev in (agent_result.events or []) if ev.get("type") == "followup_saved"), None)
    saved = saved_ev is not None
    saved_emergency = bool(saved_ev and saved_ev.get("emergency"))
    # 재예약(예약 변경/앞당김) 요청 신호 — 프론트가 슬롯 선택 흐름을 다시 띄우는 데 사용.
    rebook = any(ev.get("type") == "rebook_request" for ev in (agent_result.events or []))
    # 재예약이면 emrid로 슬롯을 직접 계산해 응답에 실어준다(세션 ref 상태와 무관하게 동작).
    rebook_slots = await _build_rebook_slots(db, request.emrid, schedule) if rebook else None
    # 예약 취소 요청 신호 — 프론트가 확인(confirm) 후 cancelSchedule을 호출하게 schedule_id를 함께 준다.
    cancel = any(ev.get("type") == "cancel_request" for ev in (agent_result.events or []))
    cancel_schedule_id = schedule.scheduleid if (cancel and schedule) else None

    # 예약 내역 보기 — 다가오는 확정 예약을 챗 카드로 보여주도록 목록을 실어준다.
    list_sched_ev = next((ev for ev in (agent_result.events or []) if ev.get("type") == "list_schedules"), None)
    show_schedules = list_sched_ev is not None
    schedules = []
    if show_schedules:
        current_only = list_sched_ev.get("current_only", False)
        if current_only:
            schedules = await _list_current_schedule(db, request.emrid)
        else:
            schedules = await _list_upcoming_schedules(db, current_user.userid, guardian.petid)

    # '문진 작성 후 예약하기' — 같은 챗에서 새 문진을 돌리도록 new_booking 플래그를 켠다(아래 commit에 포함).
    start_triage = any(ev.get("type") == "start_inchat_triage" for ev in (agent_result.events or []))
    if start_triage and chat_session is not None:
        orch = dict(chat_session.orch_state or {})
        orch["new_booking"] = True
        chat_session.orch_state = orch

    # followup 답변 다양화 상태(직전 답변 목적·이미 물은 항목)를 orch_state에 누적.
    # (이 엔드포인트는 process_turn/save_state를 안 타므로 state_patch를 수동 반영)
    _sp = agent_result.state_patch or {}
    _followup_state_keys = ("last_followup_reply_kind", "asked_followup_fields", "pending_confirmation_action")
    followup_state_changed = chat_session is not None and any(k in _sp for k in _followup_state_keys)
    if followup_state_changed:
        orch = dict(chat_session.orch_state or {})
        for k in _followup_state_keys:
            if k in _sp:
                orch[k] = _sp[k]
        chat_session.orch_state = orch

    # 내원 전 준비사항 다시 보기 — 마지막으로 저장된 준비사항 카드 items.
    show_prep = any(ev.get("type") == "show_prep" for ev in (agent_result.events or []))
    prep_instructions = _last_prep_instructions(chat_session) if show_prep else []

    # 실제로 경과가 저장됐을 때만 수의사에게 알림(잡담/병원질문 등은 저장 안 됨).
    # 응급 경과(emergency_alert)는 일반 경과와 다른 알림 타입/문구로 구분해 눈에 띄게 한다.
    if saved and schedule:
        try:
            from app.crud.alarm import create_alarm
            if saved_emergency:
                _alarm_type = "followup_urgent"
                _alarm_contents = "⚠️ 응급 경과 보고가 등록되었습니다."
            else:
                _alarm_type = "followup_received"
                _alarm_contents = "보호자가 경과 보고를 등록했습니다."
            await create_alarm(
                db=db,
                doctor_id=schedule.doctorid,
                schedule_id=schedule.scheduleid,
                alarm_type=_alarm_type,
                contents=_alarm_contents,
            )
        except Exception as e:
            logger.warning(f"[Followup] 수의사 알람 발송 실패 emrid={request.emrid}: {e}")

    # 대화 기록(chat_historyDB)에 보호자 메시지 + 챗봇 응답을 남겨 재진입 시 복원.
    # (chat_session 은 위에서 이미 로드함)
    try:
        from sqlalchemy.orm.attributes import flag_modified
        if chat_session:
            msgs = list(chat_session.messages or [])
            # 재진입 시 사진이 보이도록 image_url을 함께 저장(/chat의 add_message와 동일 형식).
            # 메시지 카드는 image_url 한 장을 렌더하므로 대표로 첫 장을 보관(나머지는 followupDB에 저장됨).
            user_msg = {"role": "user", "content": (request.message or "").strip()}
            if request.images:
                user_msg["image_url"] = request.images[0]
            msgs.append(user_msg)
            card_data = None
            if show_schedules and schedules:
                card_data = {
                    "kind": "schedules",
                    "items": [
                        {
                            "schedule_id": s["schedule_id"],
                            "when": s["when"],
                            "petName": s["pet_name"],
                            "doctorName": s["doctor_name"],
                            "hospitalName": s["hospital_name"],
                            "status": s["status"],
                        }
                        for s in schedules
                    ]
                }
            elif show_prep and prep_instructions:
                card_data = {
                    "kind": "instructions",
                    "items": prep_instructions
                }

            if agent_result.reply or card_data:
                assistant_msg = {
                    "role": "assistant",
                    "content": agent_result.reply or "",
                    "meta": {"quick_replies": agent_result.quick_replies or []}
                }
                if card_data:
                    assistant_msg["meta"]["card"] = card_data
                msgs.append(assistant_msg)
            chat_session.messages = msgs
            flag_modified(chat_session, "messages")
            if start_triage or followup_state_changed:
                flag_modified(chat_session, "orch_state")
            await db.commit()
    except Exception as e:
        logger.warning(f"[Followup] chat_history 업데이트 실패 emrid={request.emrid}: {e}")

    return {
        "code": 201,
        "message": "경과 보고가 접수되었습니다.",
        "result": {
            "reply": agent_result.reply,
            "saved": saved,
            # 경과로 저장되지 않은 입력(잡담/병원 질문 등) — 프론트 안내용.
            # (재예약·예약내역·신규예약·준비사항 등 '동작' 신호는 offtopic 아님)
            "offtopic": not any([saved, rebook, cancel, show_schedules, start_triage, show_prep]),
            # 재예약 요청이면 프론트가 슬롯 선택을 다시 띄운다.
            "rebook": rebook,
            # 재예약 슬롯(이전 문진 기반 추천 + 변경할 schedule_id) — 프론트가 그대로 렌더.
            "rebook_slots": rebook_slots,
            # 예약 취소 요청이면 프론트가 확인 후 이 schedule_id로 취소한다.
            "cancel": cancel,
            "cancel_schedule_id": cancel_schedule_id,
            "emrid": request.emrid,
            # 예약 내역 보기 — 프론트가 예약 목록 카드를 렌더(+ 예약내역 탭 안내).
            "show_schedules": show_schedules,
            "schedules": schedules,
            # '문진 작성 후 예약하기' — 프론트가 챗 입력을 문진 모드로 전환.
            "start_triage": start_triage,
            # 내원 전 준비사항 다시 보기 — 프론트가 준비사항 카드를 다시 렌더.
            "show_prep": show_prep,
            "prep_instructions": prep_instructions,
            # urgent 경과의 '더 빠른 시간 찾기'처럼 후속 행동 pill.
            "quick_replies": agent_result.quick_replies or [],
        },
    }


# 경과사진 목록 조회
@router.get("/{emrid}")
async def get_followups(
    emrid: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 소유권 검증: 본인 반려동물의 경과 기록만 조회 가능
    from app.crud.schedule import get_emrid_owner_userid
    owner_id = await get_emrid_owner_userid(db, emrid)
    if owner_id != current_user.userid:
        raise HTTPException(status_code=404, detail="경과 기록을 찾을 수 없습니다.")

    result = await db.execute(
        select(Followup).where(Followup.emrid == emrid).order_by(Followup.created_at.asc())
    )
    followups = result.scalars().all()

    return {
        "code": 200,
        "result": [
            {
                "followup_id": f.followupid,
                "images": f.images,
                "message": f.message,
                "created_at": str(f.created_at)
            }
            for f in followups
        ]
    }


# 이미지 업로드 URL 발급
@router.get("/upload/presigned-url")
async def get_presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    current_user = Depends(get_current_user)
):
    validate_file(content_type, file_size, ["image/jpeg", "image/png"], 5 * 1024 * 1024)

    from botocore.exceptions import NoCredentialsError

    from app.utils.s3 import create_presigned_put

    try:
        result = create_presigned_put(file_name, content_type, prefix="followup")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    return {"code": 200, "result": result}
