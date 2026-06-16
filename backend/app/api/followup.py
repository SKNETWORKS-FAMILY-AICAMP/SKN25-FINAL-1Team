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


def _format_followup_report(message: str | None, images: list[str] | None) -> str:
    parts: list[str] = []
    if message and message.strip():
        parts.append(f"보호자 보고: {message.strip()}")
    if images:
        parts.append(f"첨부 사진: {len(images)}장")
    return " / ".join(parts).strip()


async def run_followup_sync(followup_id: int, emrid: int, userid: int) -> dict | None:
    from app.db.session import AsyncSessionLocal
    from app.models.pet import Pet
    from app.models.triage_result import TriageResult
    from app.models.schedule import Schedule
    from app.models.followup import Followup
    from ai.agents.followup import run_followup
    from app.crud.patient import build_patient_context

    async with AsyncSessionLocal() as db:
        try:
            # 1. followup 정보 조회
            f_row = await db.execute(select(Followup).where(Followup.followupid == followup_id))
            followup = f_row.scalar_one_or_none()
            if not followup:
                return
            current_report = _format_followup_report(followup.message, followup.images)
            if not current_report:
                return

            # 같은 문진에서 지금까지 받은 경과 보고 전체를 시간순으로 전달한다.
            # 원본은 건별 저장하되, 에이전트는 여러 보고를 합친 누적 한 줄을 생성한다.
            all_f_rows = await db.execute(
                select(Followup)
                .where(Followup.emrid == emrid)
                .order_by(Followup.created_at.asc())
            )
            all_reports = [
                report
                for row in all_f_rows.scalars().all()
                if (report := _format_followup_report(row.message, row.images))
            ]

            # 2. guardian 정보 및 pet 정보 조회
            g_row = await db.execute(select(Guardian).where(Guardian.emrid == emrid))
            guardian = g_row.scalar_one_or_none()
            if not guardian:
                return
            
            pet_row = await db.execute(select(Pet).where(Pet.petid == guardian.petid))
            pet = pet_row.scalar_one_or_none()
            if not pet:
                return

            # 3. Triage 결과 조회
            t_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
            triage = t_row.scalar_one_or_none()
            triage_info = {}
            if triage:
                triage_info = {
                    "chief_complaint": triage.chief_complaint,
                    "urgency_level": triage.urgency_level,
                    "urgency_level_num": triage.urgency_level_num,
                    "symptom_keywords": triage.symptom_keywords or [],
                    "suspected_diseases": triage.suspected_diseases or [],
                    "followup_reason": triage.followup_reason or "",
                }

            # 4. 예약 정보 조회
            s_row = await db.execute(select(Schedule).where(Schedule.emrid == emrid))
            sched = s_row.scalar_one_or_none()
            appointment_slot = {}
            if sched and sched.confirmed_time:
                appointment_slot = {"date": sched.confirmed_time.date().isoformat()}

            # 5. 이전 누적 요약 조회
            prev_f_row = await db.execute(
                select(Followup)
                .where(Followup.emrid == emrid, Followup.followupid != followup_id, Followup.ai_summary.isnot(None))
                .order_by(Followup.created_at.desc())
            )
            prev_f = prev_f_row.scalars().first()
            accumulated_summary = prev_f.ai_summary if prev_f else ""

            # Payload 빌드
            from datetime import date
            age = (date.today().year - pet.birth_date.year) if pet.birth_date else None
            pet_payload = {
                "name": pet.petname,
                "species": pet.species or "dog",
                "breed": pet.breed or "알 수 없음",
                "age": age,
                "gender": pet.gender,
                "weight": float(pet.weight_kg) if pet.weight_kg else None,
            }

            # 에이전트는 전체 진료 이력 조회(교차병원 포함). 수의사 화면 표시 스코핑은 별도(api/patient.py).
            patient_context_data = await build_patient_context(db, pet.petid)

            payload = {
                "pet": pet_payload,
                "triage_info": triage_info,
                "triage_result": triage_info,
                "appointment_slot": appointment_slot,
                "accumulated_summary": accumulated_summary,
                "patient_context": patient_context_data,
                "messages": [{"role": "user", "content": report} for report in all_reports],
            }

            import asyncio
            try:
                result = await asyncio.wait_for(
                    run_followup(payload, lambda _: None, emrid, None),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"[FollowupSync] TimeoutError. Using fallback response.")
                fallback_parts = [part for part in (accumulated_summary, current_report) if part]
                fallback_summary = " / ".join(fallback_parts)[:100]
                result = {
                    "medical_summary": fallback_summary,
                    "followup_summary": fallback_summary,
                    "followup_recommended": False,
                    "guardian_message": "기록되었습니다. 분석이 지연되고 있어요. 증상 변화가 크다면 예약 일정을 다시 확인해주세요.",
                    "recommended_actions": ["keep_schedule"]
                }
            
            # DB 업데이트
            followup.ai_summary = result.get("medical_summary") or result.get("followup_summary")
            followup.emergency_alert = result.get("followup_recommended", False)
            await db.commit()
            logger.info(f"[FollowupSync] 완료 followup_id={followup_id} emrid={emrid}")
            return result
        except Exception as e:
            logger.error(f"[FollowupSync] 에이전트 실패 emrid={emrid}: {e}", exc_info=True)
            return None


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

    # triage에서 산출·저장한 단일 followup 판정값으로 서버에서도 게이트한다.
    # 프론트 can_followup 숨김만 믿지 않고 API 직접 호출도 차단한다.
    from app.models.triage_result import TriageResult
    triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == request.emrid))
    triage = triage_row.scalar_one_or_none()
    if not triage:
        raise HTTPException(status_code=404, detail="문진 결과를 찾을 수 없습니다.")
    if not triage.need_followup:
        raise HTTPException(status_code=403, detail="이 문진은 경과 보고 대상이 아닙니다.")

    # 예약 정보 조회 — 시간 가드 + 수의사 알람에 사용
    from datetime import datetime, timezone
    from app.models.schedule import Schedule
    sched_row = await db.execute(
        select(Schedule).where(Schedule.emrid == request.emrid, Schedule.deleted_at.is_(None))
    )
    schedule = sched_row.scalar_one_or_none()

    # 의도: follow-up 채팅은 예약(진료) 시간이 지나면 비활성화한다.
    if schedule and schedule.confirmed_time:
        confirmed = schedule.confirmed_time
        if confirmed.tzinfo is None:
            confirmed = confirmed.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > confirmed:
            raise HTTPException(status_code=403, detail="진료 시간이 지나 경과 보고가 마감되었습니다.")

    followup = Followup(
        emrid=request.emrid,
        userid=current_user.userid,
        images=request.images,
        message=request.message
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)

    # 의도: 경과 보고(사진/메시지)가 오면 수의사에게 바로 알림 → 대시보드에서 즉시 확인
    if schedule:
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

    ai_response = None
    if request.message or request.images:
        ai_response = await run_followup_sync(
            followup.followupid,
            request.emrid,
            current_user.userid,
        )

    # 경과보고 메시지를 chat_historyDB에도 저장 (재진입 시 기록 유지)
    try:
        from app.models.chat_history import ChatHistory
        from sqlalchemy.orm.attributes import flag_modified
        chat_row = await db.execute(
            select(ChatHistory).where(
                ChatHistory.emrid == request.emrid,
                ChatHistory.is_deleted == False,
            )
        )
        chat_session = chat_row.scalar_one_or_none()
        if chat_session:
            msgs = list(chat_session.messages or [])
            user_content = request.message or ""
            if request.images:
                user_content = (user_content + " " if user_content else "") + f"[사진 {len(request.images)}장 첨부]"
            msgs.append({"role": "user", "content": user_content.strip()})
            # followup은 개별 응대를 하지 않는다 — assistant 답변은 기록하지 않는다(재진입 시에도
            # 공감성 답변이 다시 뜨지 않도록). 보호자 보고만 남기고, 분석은 수의사용 medical_summary로만.
            chat_session.messages = msgs
            flag_modified(chat_session, "messages")
            await db.commit()
    except Exception as e:
        logger.warning(f"[Followup] chat_history 업데이트 실패 emrid={request.emrid}: {e}")

    response_payload = {
        "followup_id": followup.followupid,
    }

    if ai_response:
        response_payload.update({
            "offtopic": ai_response.get("offtopic", False),
            "followup_recommended": ai_response.get("followup_recommended", False),
            "guardian_message": ai_response.get("guardian_message", "기록되었습니다."),
            "recommended_actions": ai_response.get("recommended_actions", ["keep_schedule"]),
        })

    return {
        "code": 201,
        "message": "경과 사진이 등록되었습니다.",
        "result": response_payload
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
