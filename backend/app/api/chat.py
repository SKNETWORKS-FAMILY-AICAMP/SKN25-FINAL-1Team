from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging
from app.db.session import get_db, AsyncSessionLocal
from app.schemas.chat import ChatSessionCreate, TranslateRequest
from app.crud.chat import (
    create_chat_session, get_chat_session, get_chat_sessions_by_petid,
    delete_chat_session,
)
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.utils.file_validation import validate_file
from app.models.pet import Pet
from app.models.triage_result import TriageResult
from app.models.schedule import Schedule

from app.schemas.chat import ChatMessageRequest
from app.crud.chat import add_message

from app.services.orchestrator_service import process_turn
from app.services.translation import translate_batch

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# 초기 메세지와 pill 버튼
INITIAL_MESSAGE = (
    "안녕하세요 🐾 챗봇 메디포입니다!\n"
    "반려동물 증상을 알려주시면 적절한 진료 예약을 도와드릴게요.\n"
    "예약 관련 문의나 병원 이용 문의도 가능합니다.\n"
    "아래 항목을 선택하거나 직접 입력해주세요."
)

INITIAL_PILLS = [
    "증상을 말하고 예약할래요",
    "궁금한 게 있어요",
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
# 첨부 허용 타입 + 용량 한도 (영상은 50MB, 이미지는 5MB)
_ALLOWED_ATTACHMENT_TYPES = ["image/jpeg", "image/png", "video/mp4", "video/quicktime"]


def _attachment_max_bytes(content_type: str) -> int:
    return 50 * 1024 * 1024 if content_type.startswith("video/") else 5 * 1024 * 1024


@router.get("/upload/presigned-url")
async def get_presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    current_user=Depends(get_current_user),
):
    validate_file(content_type, file_size, _ALLOWED_ATTACHMENT_TYPES, _attachment_max_bytes(content_type))

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
    validate_file(content_type, len(body), _ALLOWED_ATTACHMENT_TYPES, _attachment_max_bytes(content_type))

    from botocore.exceptions import NoCredentialsError

    from app.utils.s3 import upload_object

    try:
        result = upload_object(file.filename or "attachment", content_type, body, prefix="chat")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    return {"code": 200, "result": result}


def _is_allowed_image_url(url: str) -> bool:
    """우리 CloudFront/S3 호스트에서 온 URL만 프록시 대상으로 허용한다(SSRF 방지)."""
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower()
    if not host:
        return False

    allowed = {
        f"{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com",
        f"s3.{settings.AWS_REGION}.amazonaws.com",
    }
    cdn_host = (urlparse(settings.CLOUDFRONT_URL or "").netloc or "").lower()
    if cdn_host:
        allowed.add(cdn_host)
    return host in allowed


# 원격 이미지를 동일 출처로 중계해 캔버스 오염(taint) 없이 편집/저장 가능하게 한다.
# (CloudFront/S3가 브라우저 origin에 CORS 헤더를 주지 않아도 동작한다.)
@router.get("/upload/proxy")
async def proxy_image(
    url: str = Query(...),
    current_user=Depends(get_current_user),
):
    if not _is_allowed_image_url(url):
        raise HTTPException(status_code=400, detail="허용되지 않은 이미지 URL입니다.")

    from botocore.exceptions import ClientError, NoCredentialsError

    from app.utils.s3 import read_object_from_url

    try:
        obj = read_object_from_url(url)
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    except (ClientError, ValueError):
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    import io

    return StreamingResponse(
        io.BytesIO(obj["body"]),
        media_type=obj["content_type"],
        headers={"Cache-Control": "private, max-age=300"},
    )


# STT — 음성 녹음(Blob)을 Groq Whisper로 전사해 텍스트 반환
@router.post("/stt")
async def speech_to_text(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="STT(Groq) 인증 정보가 설정되지 않았습니다.")

    # 오디오 검증 (코덱 파라미터 제거 후 기본 타입만 비교, 최대 10MB)
    content_type = (file.content_type or "audio/webm").split(";")[0].strip()
    body = await file.read()
    validate_file(
        content_type,
        len(body),
        ["audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/ogg"],
        10 * 1024 * 1024,
    )

    # Groq Whisper 호출 (SDK가 동기라 스레드로 분리)
    import asyncio
    from groq import Groq

    def _transcribe() -> str:
        client = Groq(api_key=settings.GROQ_API_KEY)
        result = client.audio.transcriptions.create(
            file=(file.filename or "voice.webm", body),
            model=settings.GROQ_STT_MODEL,
            language="ko",
        )
        return (result.text or "").strip()

    try:
        text = await asyncio.to_thread(_transcribe)
    except Exception as exc:
        logger.warning("[STT] 전사 실패: %s", exc)
        raise HTTPException(status_code=502, detail="음성 인식에 실패했습니다.")

    return {"code": 200, "result": {"text": text}}


# 메시지/추천 일괄 번역 — 언어 변경 시 챗봇 답변·사용자 메시지를 선택 언어로 다시 렌더링
@router.post("/translate")
async def translate_texts(
    request: TranslateRequest,
    current_user=Depends(get_current_user),
):
    translations = await translate_batch(request.texts, request.target_lang)
    return {"code": 200, "result": {"translations": translations}}


# 상담 기록 목록 조회 (offset 페이지네이션 — 무한스크롤용 10개씩)
@router.get("/sessions")
async def get_chat_sessions(
    pet_id: int = Query(...),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # limit+1개를 받아 다음 페이지 존재 여부를 판단하고, 실제 반환은 limit개로 자른다
    sessions = await get_chat_sessions_by_petid(
        db, current_user.userid, pet_id, limit=limit, offset=offset
    )
    has_more = len(sessions) > limit
    sessions = sessions[:limit]

    # 경과보고(followup)가 '활성'인 세션 표시용 — 예약(확정)이 있고 진료 시작 1시간 전까지인 emrid.
    # need_followup 게이팅 폐기 → 상세의 can_followup과 동일하게 예약 기준만 본다.
    from datetime import datetime, timezone, timedelta
    emrids = [s.emrid for s in sessions if s.emrid is not None]
    followup_active_emrids: set[int] = set()
    if emrids:
        sched_rows = await db.execute(
            select(Schedule).where(
                Schedule.emrid.in_(emrids),
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
            # 진료 시작 1시간 전까지만 활성.
            if now <= confirmed - timedelta(hours=1):
                followup_active_emrids.add(sched.emrid)

    return {
        "code": 200,
        # has_more: 다음 페이지(스크롤 더 로딩)가 있는지 — 프론트 무한스크롤 종료 판단용
        "has_more": has_more,
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
        from datetime import datetime, timezone, timedelta
        schedule_row = await db.execute(
            select(Schedule).where(Schedule.emrid == emrid, Schedule.deleted_at.is_(None))
        )
        schedule = schedule_row.scalar_one_or_none()
        # follow-up은 진료 시작 1시간 전에 마감 → 그 전까지만 '열림'.
        followup_open_time = True
        if schedule and schedule.confirmed_time:
            confirmed = schedule.confirmed_time
            if confirmed.tzinfo is None:
                confirmed = confirmed.replace(tzinfo=timezone.utc)
            followup_open_time = datetime.now(timezone.utc) <= confirmed - timedelta(hours=1)
        # need_followup 게이팅 폐기 — 예약(확정)만 있으면 경과보고 가능(라이브=재진입 일관).
        can_followup = bool(schedule and schedule.confirmed_time and schedule.status != "COMPLETED" and followup_open_time)
        # 예약 확정 = 취소되지 않은 schedule에 확정 시각이 존재.
        booking_complete = bool(schedule and schedule.confirmed_time and schedule.status != "CANCELLED")
        # 경과보고 마감 = 예약은 있으나 진료 시작 시간이 지났거나 완료된 상태.
        #  → 재진입 시 입력창 대신 '마감' 안내를 띄우기 위한 신호.
        followup_closed = bool(schedule and schedule.confirmed_time and not can_followup)

    messages = session.messages or []

    # 이어가기 판정: 문진 미완료 → 문진 재개 / 완료·예약 미확정 → 슬롯 선택 재개
    resumable_triage = bool(not session.is_complete and messages)
    resumable_schedule = bool(session.is_complete and emrid and not booking_complete)

    # 재진입 시 pill 복원 — 마지막 챗봇 질문에 저장된 quick_replies
    resume_quick_replies: list = []
    if resumable_triage:
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "assistant":
                resume_quick_replies = (m.get("meta") or {}).get("quick_replies") or []
                break

    return {
        "code": 200,
        "result": {
            "session_id": session.id,
            "pet_id": session.petid,
            "emrid": emrid,
            "messages": messages,
            "keywords": session.keywords or [],
            "is_complete": session.is_complete,
            "resumable_triage": resumable_triage,
            "resumable_schedule": resumable_schedule,
            "resume_quick_replies": resume_quick_replies,
            "can_followup": can_followup,
            "followup_closed": followup_closed,
            "booking_complete": booking_complete,
            "created_at": str(session.created_at),
        },
    }


# 슬롯 선택 재개 — 저장된 TriageResult로 triage_info 복원(프론트가 추천 슬롯 재요청)
@router.post("/sessions/{session_id}/resume-schedule")
async def resume_schedule(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다.")

    emrid = session.emrid
    triage_info: dict = {}
    if emrid is not None:
        triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
        triage = triage_row.scalar_one_or_none()
        if triage:
            triage_info = {
                "urgency": triage.urgency_level,
                "urgency_level_num": triage.urgency_level_num,
                "chief_complaint": triage.chief_complaint,
                "chief_complaints": [triage.chief_complaint] if triage.chief_complaint else [],
                "suspected_diseases": triage.suspected_diseases or [],
                "suspected_conditions": triage.suspected_diseases or [],
                "symptom_summary": triage.symptom_summary,
                "triage_summary": triage.symptom_summary,
            }

    return {
        "code": 200,
        "result": {"emrid": emrid, "triage_info": triage_info, "schedule_task_id": None},
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
    current_user=Depends(get_current_user),
):
    # SSE: event_stream()은 엔드포인트 함수가 리턴된 뒤 실행되므로 Depends(get_db) 세션을
    # 쓰면 스트리밍 시작 전에 세션이 닫혀 커넥션 누수("non-checked-in connection ...
    # will be terminated")가 난다. 제너레이터가 자체 세션을 열어 끝까지 소유하게 한다.
    async def event_stream():

        try:
            # 진행 단계(status) 이벤트는 즉시 전달, 최종 결과(result)는 보관
            result = None
            async with AsyncSessionLocal() as db:
                async for event in process_turn(
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

            # 문진 완료 → emrid(예약용) + 슬롯 추천에 쓸 트리아지 결과 전달
            if result.get("is_complete"):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "triage_complete",
                            "emrid": result.get("emrid"),
                            "data": {
                                "is_triage_complete": True,
                                "symptom_keywords": result.get("keywords") or [],
                                "urgency": result.get("urgency"),
                                "chief_complaints": result.get("chief_complaints") or [],
                                "suspected_conditions": result.get("suspected_conditions") or [],
                                "triage_summary": result.get("triage_summary"),
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