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

# NOTE: 옛 followup AI 요약(ai/agents/followup.py · run_followup_sync)은 제거됨.
# 경과 보고의 AI 처리는 v2 챗봇의 followup_filter(대화 내)로 이관. 이 엔드포인트는
# 경과 '저장/조회/업로드'만 담당한다(수의사 알람 포함).


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

    # follow-up은 예약(진료) 시간이 지나면 비활성화한다.
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

    # 경과 보고가 오면 수의사에게 바로 알림 → 대시보드에서 즉시 확인
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
            chat_session.messages = msgs
            flag_modified(chat_session, "messages")
            await db.commit()
    except Exception as e:
        logger.warning(f"[Followup] chat_history 업데이트 실패 emrid={request.emrid}: {e}")

    return {
        "code": 201,
        "message": "경과 사진이 등록되었습니다.",
        "result": {"followup_id": followup.followupid},
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
