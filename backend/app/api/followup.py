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
    from datetime import datetime, timezone, timedelta
    from app.models.schedule import Schedule
    sched_row = await db.execute(
        select(Schedule).where(Schedule.emrid == request.emrid, Schedule.deleted_at.is_(None))
    )
    schedule = sched_row.scalar_one_or_none()

    # follow-up은 진료 시작 'FOLLOWUP_CLOSE_BEFORE'(1시간) 전에 마감한다.
    # (chat.py의 can_followup/active 목록 판정과 동일 기준)
    if schedule and schedule.confirmed_time:
        confirmed = schedule.confirmed_time
        if confirmed.tzinfo is None:
            confirmed = confirmed.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > confirmed - timedelta(hours=1):
            raise HTTPException(status_code=403, detail="진료 시작 1시간 전이 되어 경과 보고가 마감되었습니다.")

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
            db=db,
        )

    agent_result = await run_turn(ctx)
    saved = any(ev.get("type") == "followup_saved" for ev in (agent_result.events or []))
    # 재예약(예약 변경/앞당김) 요청 신호 — 프론트가 슬롯 선택 흐름을 다시 띄우는 데 사용.
    rebook = any(ev.get("type") == "rebook_request" for ev in (agent_result.events or []))

    # 실제로 경과가 저장됐을 때만 수의사에게 알림(잡담/병원질문 등은 저장 안 됨).
    if saved and schedule:
        try:
            from app.crud.alarm import create_alarm
            await create_alarm(
                db=db,
                doctor_id=schedule.doctorid,
                schedule_id=schedule.scheduleid,
                alarm_type="followup_received",
                contents="보호자가 경과 보고를 등록했습니다.",
            )
        except Exception as e:
            logger.warning(f"[Followup] 수의사 알람 발송 실패 emrid={request.emrid}: {e}")

    # 대화 기록(chat_historyDB)에 보호자 메시지 + 챗봇 응답을 남겨 재진입 시 복원.
    # (chat_session 은 위에서 이미 로드함)
    try:
        from sqlalchemy.orm.attributes import flag_modified
        if chat_session:
            msgs = list(chat_session.messages or [])
            user_content = request.message or ""
            if request.images:
                user_content = (user_content + " " if user_content else "") + f"[사진 {len(request.images)}장 첨부]"
            msgs.append({"role": "user", "content": user_content.strip()})
            if agent_result.reply:
                msgs.append({"role": "assistant", "content": agent_result.reply})
            chat_session.messages = msgs
            flag_modified(chat_session, "messages")
            await db.commit()
    except Exception as e:
        logger.warning(f"[Followup] chat_history 업데이트 실패 emrid={request.emrid}: {e}")

    return {
        "code": 201,
        "message": "경과 보고가 접수되었습니다.",
        "result": {
            "reply": agent_result.reply,
            "saved": saved,
            # 경과로 저장되지 않은 입력(잡담/병원 질문 등) — 프론트 안내용. (재예약은 offtopic 아님)
            "offtopic": not saved and not rebook,
            # 재예약 요청이면 프론트가 슬롯 선택을 다시 띄운다.
            "rebook": rebook,
            "emrid": request.emrid,
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
