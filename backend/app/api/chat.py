from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging
from langchain_openai import ChatOpenAI
from app.db.session import get_db
from app.schemas.chat import ChatSessionCreate, TranslateRequest
from app.crud.chat import (
    create_chat_session, get_chat_session, get_chat_sessions_by_petid,
    delete_chat_session,
)
from app.core.dependencies import get_current_user
from app.utils.file_validation import validate_file
from app.core.config import settings
from app.models.pet import Pet
from app.models.triage_result import TriageResult
from app.models.schedule import Schedule

from app.schemas.chat import ChatMessageRequest
from app.crud.chat import add_message

from app.services.chat_service import (
    process_chat_message,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# 초기 메세지와 pill 버튼
INITIAL_MESSAGE = (
    "안녕하세요 🐾\n"
    "반려동물의 증상을 알려주시면 예약을 도와드릴게요.\n"
    "아래 항목을 선택하거나 직접 입력해주세요."
)

INITIAL_PILLS = [
    "기침",
    "발작",
    "피부",
    "기타"
]


# 챗봇 세션 시작
@router.post("/sessions", status_code=201)
async def start_chat_session(
    request: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Pet).where(Pet.petid == request.pet_id, Pet.userid == current_user.userid)
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    session = await create_chat_session(db, current_user.userid, request.pet_id)

    return {
        "code": 201,
        "result": {
            "session_id": session.id,
            "pet_name": pet.petname,
            "profile_image": pet.profile_image,
            "initial_message": INITIAL_MESSAGE,
            "initial_pills": INITIAL_PILLS,
        },
    }


# 이미지 업로드 URL 발급
@router.get("/upload/presigned-url")
async def get_presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    current_user=Depends(get_current_user),
):
    validate_file(content_type, file_size, ["image/jpeg", "image/png", "video/mp4"], 5 * 1024 * 1024)

    from botocore.exceptions import NoCredentialsError

    from app.utils.s3 import create_presigned_put

    try:
        result = create_presigned_put(file_name, content_type, prefix="chat")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    return {"code": 200, "result": result}


@router.post("/upload/file")
async def upload_chat_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    content_type = file.content_type or "application/octet-stream"
    body = await file.read()
    validate_file(content_type, len(body), ["image/jpeg", "image/png", "video/mp4"], 5 * 1024 * 1024)

    from botocore.exceptions import NoCredentialsError

    from app.utils.s3 import upload_object

    try:
        result = upload_object(file.filename or "attachment", content_type, body, prefix="chat")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    return {"code": 200, "result": result}


_LANG_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Simplified Chinese",
}


async def _translate_batch(texts: list[str], target: str) -> list[str]:
    """주어진 문구들을 target 언어로 일괄 번역한다. 실패 시 원문을 그대로 반환."""
    target = target if target in _LANG_NAMES else "en"
    items = [(i, text) for i, text in enumerate(texts) if text and text.strip()]
    translations: list[str] = list(texts)
    if not items:
        return translations

    try:
        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL or "gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.0,
            timeout=30.0,
            max_retries=1,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        numbered = "\n".join(f'{i}: {text}' for i, text in items)
        response = await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are a translation engine. Translate each numbered line into {_LANG_NAMES[target]}. "
                        "Keep meaning, tone, emojis, numbers, dates and times unchanged. "
                        "If a line is already in the target language, return it unchanged. "
                        'Return ONLY a JSON object of the form {"translations": {"<index>": "<translated text>"}} '
                        "using the same indices you were given."
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            config={"run_name": "chat_translate"},
        )
        raw = response.content if isinstance(response.content, str) else "{}"
        parsed = json.loads(raw or "{}")
        mapping = parsed.get("translations", parsed)
        if isinstance(mapping, dict):
            for i, _ in items:
                value = mapping.get(str(i), mapping.get(i))
                if isinstance(value, str) and value.strip():
                    translations[i] = value
    except Exception as exc:
        # 번역 실패 시 원문을 그대로 반환 — 화면이 비지 않도록 한다.
        logger.warning("[Chat/Translate] failed target=%s: %s", target, exc, exc_info=True)

    return translations


# 메시지/추천 일괄 번역 — 언어 변경 시 챗봇 답변·사용자 메시지를 선택 언어로 다시 렌더링
@router.post("/translate")
async def translate_texts(
    request: TranslateRequest,
    current_user=Depends(get_current_user),
):
    translations = await _translate_batch(request.texts, request.target_lang)
    return {"code": 200, "result": {"translations": translations}}


# 상담 기록 목록 조회
@router.get("/sessions")
async def get_chat_sessions(
    pet_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sessions = await get_chat_sessions_by_petid(db, current_user.userid, pet_id)

    # 경과보고(followup)가 '활성'인 세션 표시용 — need_followup이고 진료 시작 시간 전인 emrid.
    # 상세의 can_followup과 동일 기준. 목록에 작은 마커를 달아 보호자가 식별할 수 있게 한다.
    from datetime import datetime, timezone
    emrids = [s.emrid for s in sessions if s.emrid is not None]
    followup_active_emrids: set[int] = set()
    if emrids:
        triage_rows = await db.execute(
            select(TriageResult.emrid).where(
                TriageResult.emrid.in_(emrids), TriageResult.need_followup.is_(True)
            )
        )
        need_emrids = {row[0] for row in triage_rows.all()}
        if need_emrids:
            sched_rows = await db.execute(
                select(Schedule).where(
                    Schedule.emrid.in_(need_emrids),
                    Schedule.deleted_at.is_(None),
                    Schedule.status != "COMPLETED",
                    Schedule.confirmed_time.isnot(None),
                )
            )
            now = datetime.now(timezone.utc)
            for sched in sched_rows.scalars().all():
                confirmed = sched.confirmed_time
                if confirmed.tzinfo is None:
                    confirmed = confirmed.replace(tzinfo=timezone.utc)
                if now <= confirmed:
                    followup_active_emrids.add(sched.emrid)

    return {
        "code": 200,
        "result": [
            {
                "session_id": session.id,
                "keywords": session.keywords or [],
                "created_at": str(session.created_at.date()),
                "status": "진료완료" if session.is_complete else "상담중",
                "followup_active": session.emrid in followup_active_emrids,
            }
            for session in sessions
        ],
    }


# 특정 세션 상세 조회
@router.get("/sessions/{session_id}")
async def get_chat_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다.")

    can_followup = False
    booking_complete = False
    followup_closed = False
    emrid = session.emrid
    if emrid is not None:
        from datetime import datetime, timezone
        triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
        triage = triage_row.scalar_one_or_none()
        schedule_row = await db.execute(
            select(Schedule).where(Schedule.emrid == emrid, Schedule.deleted_at.is_(None))
        )
        schedule = schedule_row.scalar_one_or_none()
        need_followup = bool(triage and triage.need_followup)
        appointment_not_passed = True
        if schedule and schedule.confirmed_time:
            confirmed = schedule.confirmed_time
            if confirmed.tzinfo is None:
                confirmed = confirmed.replace(tzinfo=timezone.utc)
            appointment_not_passed = datetime.now(timezone.utc) <= confirmed
        can_followup = bool(need_followup and schedule and schedule.status != "COMPLETED" and appointment_not_passed)
        # 예약 확정 = 취소되지 않은 schedule에 확정 시각이 존재.
        booking_complete = bool(schedule and schedule.confirmed_time and schedule.status != "CANCELLED")
        # 경과보고 마감 = followup 대상이었으나 진료 시작 시간이 지났거나(또는 완료) 더는 보낼 수 없는 상태.
        #  → 재진입 시 입력창 대신 '마감' 안내를 띄우기 위한 신호.  
        followup_closed = bool(need_followup and schedule and schedule.confirmed_time and not can_followup)

    messages = session.messages or []

    return {
        "code": 200,
        "result": {
            "session_id": session.id,
            "pet_id": session.petid,
            "emrid": emrid,
            "messages": messages,
            "keywords": session.keywords or [],
            "is_complete": session.is_complete,
            "can_followup": can_followup,
            "followup_closed": followup_closed,
            "booking_complete": booking_complete,
            "created_at": str(session.created_at),
        },
    }


# 상담 기록 삭제
@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다.")

    if session.userid != current_user.userid:
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")

    await delete_chat_session(db, session)
    return {"code": 200, "message": "상담 기록이 삭제되었습니다."}


# 메시지 전송 (사용자 → 챗봇)
@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):

    async def event_stream():

        try:

            # 진행 단계(status) 이벤트는 즉시 전달, 최종 결과(result)는 보관
            result = None
            async for event in process_chat_message(
                db=db,
                session_id=session_id,
                userid=current_user.userid,
                request=request,
            ):
                # 진행 상태 알림(이미지 분석중/응답 생성중) 그대로 흘려보냄
                if event["type"] == "status":
                    yield (
                        "data: "
                        + json.dumps(event, ensure_ascii=False)
                        + "\n\n"
                    )
                    continue
                # 최종 결과 보관
                if event["type"] == "result":
                    result = event["result"]

            message_payload = {
                "type": "message",
                "content": result["reply"],
            }

            yield (
                "data: "
                + json.dumps(
                    message_payload,
                    ensure_ascii=False,
                )
                + "\n\n"
            )

            # 답변 후보 pill 전송
            quick_replies = result.get("quick_replies") or []
            if quick_replies:
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "quick_replies", "options": quick_replies},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            # 문진 완료 시 제목(주요증상) 실시간 반영용 이벤트
            if result.get("is_complete"):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "triage_complete",
                            "data": {
                                "is_triage_complete": True,
                                "symptom_keywords": result.get("keywords") or [],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            done_payload = {
                "type": "done",
            }

            yield (
                "data: "
                + json.dumps(
                    done_payload,
                    ensure_ascii=False,
                )
                + "\n\n"
            )

        except Exception as e:

            error_payload = {
                "type": "error",
                "message": str(e),
            }

            yield (
                "data: "
                + json.dumps(
                    error_payload,
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )