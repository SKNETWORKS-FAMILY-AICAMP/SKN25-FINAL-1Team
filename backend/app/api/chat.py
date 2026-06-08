from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import asyncio
import logging
import re
import uuid
import base64
from datetime import date
from langchain_openai import ChatOpenAI
from ai.observability import get_langfuse_handler
from app.db.session import get_db
from app.schemas.chat import ChatSessionCreate, ChatMessageRequest, TranslateRequest
from app.crud.chat import (
    create_chat_session, get_chat_session, get_chat_sessions_by_petid,
    add_message, delete_chat_session, update_session_complete,
    create_triage_guardian, update_session_emrid, update_guardian_category,
)
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.pet import Pet
from app.models.triage_result import TriageResult
from app.models.schedule import Schedule
from app.crud.triage import build_triage_result
from ai.agents.triage import INITIAL_MESSAGE, INITIAL_PILLS, content_text as triage_content_text
from ai.agents.triage import run_triage_turn
from ai.tasks import _task_store, cleanup_task_after_ttl, safe_create_task, TaskStatus, PipelineState

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# Shadow Triage / Zero-Liability:
# 보호자 프론트엔드로는 진단성 정보(응급도 라벨·red_flags·추측질환·VTL 근거 등)를
# 절대 내려보내지 않는다. 전체 triage 결과는 triage_resultDB에 저장되어 수의사만 열람한다.
# 클라이언트에는 예약 흐름 제어에 필요한 최소 필드만 전달한다.
_GUARDIAN_SAFE_FIELDS = ("is_triage_complete", "urgency_level_num", "need_followup", "symptom_keywords")
_INITIAL_MESSAGE = INITIAL_MESSAGE
_INITIAL_PILLS = INITIAL_PILLS


def _photo_predictions_from_analysis(analysis: dict | None, image_url: str | None = None) -> list[dict]:
    """chart/수의사용 payload에 남길 사진 모델 예측값."""
    if not analysis:
        return []
    predictions: list[dict] = []
    for key, model_type in (("skin", "skin"), ("eye", "eye")):
        item = analysis.get(key)
        if not isinstance(item, dict) or item.get("error"):
            continue
        predictions.append({
            "model_type": model_type,
            "prediction": item.get("top_1"),
            "top_class": item.get("top_class"),
            "confidence": item.get("top_confidence"),
            "details": item.get("details") or [],
            "image_url": image_url,
        })
    return predictions


def _session_photo_predictions(session) -> list[dict]:
    predictions: list[dict] = []
    for message in session.messages or []:
        if not isinstance(message, dict):
            continue
        predictions.extend(
            _photo_predictions_from_analysis(
                message.get("photo_analysis"),
                message.get("image_url"),
            )
        )
    return predictions


def _mime_type_from_url(image_url: str) -> str:
    lower = image_url.lower().split("?", 1)[0]
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _image_data_url_from_s3_url(image_url: str) -> str:
    from app.utils.s3 import read_object_bytes_from_url

    image_bytes = read_object_bytes_from_url(image_url)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{_mime_type_from_url(image_url)};base64,{encoded}"


async def _analyze_chat_photo(image_url: str, user_text: str) -> dict | None:
    try:
        from app.utils.s3 import read_object_bytes_from_url
        from ai.services.vision_model import vision_service

        image_bytes = read_object_bytes_from_url(image_url)
        analysis = {"skin": vision_service.analyze_skin(image_bytes)}

        text = user_text or ""
        if any(keyword in text for keyword in ("눈", "안구", "눈물", "충혈", "각막")):
            analysis["eye"] = vision_service.analyze_eye(image_bytes)

        logger.info(
            "[Vision/Chat] analyzed image_url=%s skin=%s eye=%s",
            image_url,
            analysis.get("skin", {}).get("top_class"),
            analysis.get("eye", {}).get("top_class") if analysis.get("eye") else None,
        )
        return analysis
    except Exception as exc:
        logger.warning("[Vision/Chat] image analysis failed image_url=%s: %s", image_url, exc, exc_info=True)
        return {"skin": {"error": "첨부 사진 분석에 실패했습니다."}}


async def _describe_chat_photo(image_url: str, user_text: str) -> dict | None:
    try:
        llm = ChatOpenAI(
            model=settings.OPENAI_VISION_MODEL or settings.OPENAI_MODEL or "gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.0,
            timeout=45.0,
            max_retries=0,
            model_kwargs={"max_completion_tokens": 400, "response_format": {"type": "json_object"}},
        )
        response = await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "당신은 반려동물 사진에서 보이는 특징만 관찰하는 보조 모델입니다. "
                        "진단명이나 확정 판단은 하지 마세요. 한국어 JSON만 출력하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "보호자 말: "
                                f"{user_text or '첨부 사진만 전달됨'}\n"
                                "사진에서 명확히 보이는 변화만 적어주세요. "
                                "붉은 부위, 돌출, 털 빠짐, 상처처럼 보이는 부분, 진물/출혈처럼 보이는 흔적이 있으면 포함하세요.\n"
                                "형식: {\"visible_changes\":[\"...\"],\"lesion_location\":\"...\",\"question_focus\":\"...\"}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _image_data_url_from_s3_url(image_url),
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            config={"run_name": "vision_chat", "callbacks": [get_langfuse_handler()]},
        )
        raw = response.content if isinstance(response.content, str) else "{}"
        parsed = json.loads(raw or "{}")
        logger.info("[Vision/Chat] visual observation=%s", parsed)
        return parsed
    except Exception as exc:
        logger.warning("[Vision/Chat] visual observation failed image_url=%s: %s", image_url, exc, exc_info=True)
        return None


def _guardian_safe_triage(info: dict | None) -> dict | None:
    """보호자 클라이언트로 전달할 triage 정보에서 진단성 필드를 제거한다."""
    if not isinstance(info, dict):
        return info
    return {k: info.get(k) for k in _GUARDIAN_SAFE_FIELDS if k in info}


async def _run_triage_complete_background(
    task_id: str,
    emrid: int,
    pet_payload: dict,
    collected_info: dict,
    patient_context: dict,
    messages: list[dict],
) -> None:
    """문진 완료 직후 백그라운드 — LangGraph triage_complete 그래프.

    triage요약(LLM, symptom_summary 갱신) ∥ schedule(슬롯 계산)을 병렬 실행한다.
    schedule 결과는 task_id(task_store)로 SSE 폴링되며, 요약은 DB를 갱신한다.
    """
    logger.info(f"[TriageComplete BG] start task_id={task_id} emrid={emrid}")
    try:
        from ai.graph import triage_complete_graph
        await triage_complete_graph.ainvoke({
            "emrid": emrid,
            "schedule_task_id": task_id,
            "pet": pet_payload,
            "collected_info": collected_info,
            "patient_context": patient_context,
            "messages": messages,
        })
    except Exception as exc:
        logger.error(f"[TriageComplete BG] failed task_id={task_id}: {exc}", exc_info=True)
        _task_store[task_id] = {"status": "error", "detail": str(exc)}
    finally:
        safe_create_task(
            cleanup_task_after_ttl(task_id),
            name=f"cleanup:{task_id}",
        )


async def _complete_and_schedule(
    db, session, collected_info: dict, pet_payload: dict, patient_context_data: dict,
) -> tuple[int, str]:
    """문진 완료 공통 처리 — TriageResult 저장 + Guardian + Schedule BG 실행.

    red flag 단축과 walker 종료 양쪽에서 재사용. (emrid, schedule_task_id) 반환.
    """
    keywords = collected_info.get("symptom_keywords") or []
    photo_predictions = _session_photo_predictions(session)
    if photo_predictions:
        collected_info["photo_predictions"] = photo_predictions
        collected_info["need_photo"] = False
    await update_session_complete(db, session, keywords)

    guardian = await create_triage_guardian(db, session.petid)
    emrid = guardian.emrid
    await update_session_emrid(db, session, emrid)

    try:
        db.add(build_triage_result(emrid, collected_info))
        await db.commit()
        logger.info(f"[TriageResult] saved emrid={emrid}")
        await update_guardian_category(
            db, emrid,
            symptom_keywords=collected_info.get("symptom_keywords") or [],
            chief_complaint=collected_info.get("chief_complaint") or "",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"[TriageResult] save failed emrid={emrid}: {e}")

    # 요약 노드에 넘길 전체 대화(보호자+챗봇)
    session_messages = [
        {"role": m.get("role"), "content": triage_content_text(m.get("content"))}
        for m in (session.messages or [])
        if m.get("role") in ("user", "assistant") and triage_content_text(m.get("content"))
    ]

    schedule_task_id = str(uuid.uuid4())
    _task_store[schedule_task_id] = {"status": TaskStatus.QUEUED, "step": ""}
    logger.info(
        "[TriageComplete BG] queued pipeline_state=%s task_id=%s emrid=%s",
        PipelineState.SCHEDULE_PENDING, schedule_task_id, emrid,
    )
    safe_create_task(
        _run_triage_complete_background(
            schedule_task_id, emrid, pet_payload, collected_info, patient_context_data, session_messages,
        ),
        task_id=schedule_task_id,
        name="triage_complete_bg",
    )
    return emrid, schedule_task_id


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
            "initial_message": _INITIAL_MESSAGE,
            "initial_pills": _INITIAL_PILLS,
            "initial_multi": False,
        },
    }


# 챗봇 메시지 전송 (SSE 스트리밍)
@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not request.content and not request.image_url:
        raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")

    ui_lang = request.lang if request.lang in _LANG_NAMES else "ko"

    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다.")

    pet_result = await db.execute(select(Pet).where(Pet.petid == session.petid))
    pet = pet_result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    # 한국어 triage 엔진이 이해하도록, 한글이 없는 입력(영어/일본어/중국어 등 자유 입력)은
    # 한국어로 번역해 처리한다. 저장·표시는 보호자가 보낸 원문 그대로 유지한다.
    # (pill 클릭은 프론트가 한국어 원문을 보내므로 한글이 있어 번역 대상이 아니다.)
    processing_text = request.content or ""
    if processing_text.strip() and not _has_hangul(processing_text):
        processing_text = (await _translate_batch([processing_text], "ko"))[0]

    photo_analysis = None
    if request.image_url:
        photo_analysis = await _analyze_chat_photo(request.image_url, processing_text)
        visual_observation = await _describe_chat_photo(request.image_url, processing_text)
        if visual_observation:
            photo_analysis = photo_analysis or {}
            photo_analysis["visual_observation"] = visual_observation

    await add_message(db, session, "user", request.content, request.image_url, photo_analysis=photo_analysis)

    from app.crud.patient import build_patient_context
    
    patient_context_data = await build_patient_context(db, session.petid)

    # event_stream 클로저에서 사용할 반려동물 정보 딕셔너리
    pet_age = (date.today().year - pet.birth_date.year) if pet.birth_date else None
    pet_payload = {
        "name": pet.petname,
        "species": pet.species or "dog",
        "breed": pet.breed or "알 수 없음",
        "age": pet_age,
        "gender": pet.gender,
        "weight": float(pet.weight_kg) if pet.weight_kg else None,
    }

    async def event_stream():
        try:
            CHUNK = 10

            async def stream_msg(text: str):
                for i in range(0, len(text), CHUNK):
                    yield f"data: {json.dumps({'type': 'message', 'content': text[i:i + CHUNK]}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)

            done_event = f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            result = await run_triage_turn(
                db=db,
                messages=session.messages or [],
                raw_user_text=processing_text,
                image_url=request.image_url,
                photo_analysis=photo_analysis,
                species=pet.species or "dog",
                gender=pet.gender,
            )

            # 어시스턴트 메시지 meta에 현재 quick_replies(pill)를 함께 저장한다.
            # → 세션을 나갔다 돌아와도 마지막 pill을 그대로 복원(req4, FREEFORM 포함).
            meta_to_store = result.meta
            if result.quick_replies:
                meta_to_store = {**(result.meta or {}), "quick_replies": list(result.quick_replies)}
            # DB에는 항상 한국어 원문을 저장한다(수의사 차트 + 추후 언어 전환 재번역의 원본).
            await add_message(db, session, "assistant", result.reply, meta=meta_to_store)

            # UI 언어가 한국어가 아니면, 답변과 추천(pill)을 그 언어로 미리 번역해
            # '번역된 텍스트를 바로 스트리밍'한다 → 한국어 플래시 없이 빠르게 표시.
            reply_text = result.reply
            qr_display = list(result.quick_replies or [])
            if ui_lang != "ko":
                batch = await _translate_batch([result.reply, *qr_display], ui_lang)
                reply_text = batch[0]
                qr_display = batch[1:]

            async for c in stream_msg(reply_text):
                yield c

            # 번역이 실제로 적용된 경우에만 contentLang을 태깅한다.
            # (번역 실패로 한국어가 그대로 스트리밍되면 프론트가 한국어 원문으로 재번역하도록 둔다.)
            if ui_lang != "ko" and reply_text != result.reply:
                yield f"data: {json.dumps({'type': 'message_meta', 'source': result.reply, 'lang': ui_lang}, ensure_ascii=False)}\n\n"

            if result.is_complete and result.collected_info:
                emrid, sched = await _complete_and_schedule(
                    db, session, result.collected_info, pet_payload, patient_context_data
                )
                yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(result.collected_info), 'emrid': emrid, 'schedule_task_id': sched}, ensure_ascii=False)}\n\n"
                yield done_event
                return

            if result.quick_replies:
                payload = {
                    "type": "quick_replies",
                    "options": list(result.quick_replies),  # 라우팅용 한국어 원문
                    "options_display": qr_display,            # 표시용 번역본(프론트 캐시 프라임)
                    "multi": result.multi,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield done_event

        except Exception as e:
            # 내부 예외 메시지를 그대로 노출하지 않고 사용자 친화적 안내로 대체한다.
            logger.error(f"[Chat] event_stream 실패 session_id={session_id}: {e}", exc_info=True)
            friendly = "일시적인 오류로 답변을 불러오지 못했어요. 잠시 후 다시 시도해주세요."
            yield f"data: {json.dumps({'type': 'error', 'message': friendly}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 이미지 업로드 URL 발급
@router.get("/upload/presigned-url")
async def get_presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    current_user=Depends(get_current_user),
):
    allowed_types = ["image/jpeg", "image/png", "video/mp4"]
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="이미지(JPG, PNG) 또는 영상(MP4) 파일만 업로드 가능합니다.")

    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 5MB 이하만 업로드 가능합니다.")

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
    allowed_types = ["image/jpeg", "image/png", "video/mp4"]
    content_type = file.content_type or "application/octet-stream"
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="이미지(JPG, PNG) 또는 영상(MP4) 파일만 업로드 가능합니다.")

    body = await file.read()
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 5MB 이하만 업로드 가능합니다.")

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


_HANGUL_RE = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")


def _has_hangul(text: str | None) -> bool:
    return bool(text and _HANGUL_RE.search(text))


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
            config={"run_name": "chat_translate", "callbacks": [get_langfuse_handler()]},
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
    return {
        "code": 200,
        "result": [
            {
                "session_id": session.id,
                "keywords": session.keywords or [],
                "created_at": str(session.created_at.date()),
                "status": "진료완료" if session.is_complete else "상담중",
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
    emrid = session.emrid
    if emrid is not None:
        from datetime import datetime, timezone
        triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
        triage = triage_row.scalar_one_or_none()
        schedule_row = await db.execute(
            select(Schedule).where(Schedule.emrid == emrid, Schedule.deleted_at.is_(None))
        )
        schedule = schedule_row.scalar_one_or_none()
        # 게이트는 triage 때 산출·저장된 단일 판정값을 그대로 읽는다(점수 ≤2 재계산 폐기).
        # 산출 기준: ai.triage.engine.compute_need_followup('동적 증상군' 여부).
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

    messages = session.messages or []

    # 재개(resume) 신호 — 나갔다 돌아와도 '활성' 상태로 이어가야 하는 채팅 판별.
    #  · resumable_triage  : 문진 미완료(is_complete=False) → 라이브 문진으로 이어서 진행
    #  · resumable_schedule: 문진 완료·예약 미확정 → 슬롯 선택 단계 재개(서버에서 schedule 재실행)
    has_user_message = any(
        isinstance(m, dict) and m.get("role") == "user" for m in messages
    )
    resumable_triage = bool(not session.is_complete and has_user_message)
    resumable_schedule = bool(session.is_complete and emrid is not None and not booking_complete)

    # 라이브 문진 재개 시 마지막에 보여줬던 pill(quick_replies)을 함께 내려 보낸다.
    # 1순위: 어시스턴트 메시지 meta에 저장된 quick_replies(FREEFORM 동적 chips 포함).
    # 2순위: KB 노드 pill_labels (구버전 메시지 호환).
    resume_quick_replies: list[str] = []
    if resumable_triage:
        try:
            from ai.triage import engine as triage_engine
            last_meta = next(
                (m.get("meta") for m in reversed(messages)
                 if isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("meta"), dict)),
                None,
            )
            stored = (last_meta or {}).get("quick_replies")
            if isinstance(stored, list) and stored:
                resume_quick_replies = [str(s) for s in stored]
            else:
                node_id = (last_meta or {}).get("node_id") or triage_engine.START_NODE
                pet_row = await db.execute(select(Pet).where(Pet.petid == session.petid))
                pet_obj = pet_row.scalar_one_or_none()
                resume_quick_replies = triage_engine.pill_labels(
                    node_id, pet_obj.species if pet_obj else None
                )
        except Exception:
            resume_quick_replies = []

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
            "booking_complete": booking_complete,
            "resumable_triage": resumable_triage,
            "resumable_schedule": resumable_schedule,
            "resume_quick_replies": resume_quick_replies,
            "created_at": str(session.created_at),
        },
    }


def _triage_result_to_dict(triage) -> dict:
    """저장된 TriageResult ORM 행을 schedule 에이전트 입력 dict로 복원한다."""
    return {
        "is_triage_complete": True,
        "urgency_level": triage.urgency_level,
        "urgency_level_num": triage.urgency_level_num,
        "vtl_basis": triage.vtl_basis,
        "red_flags": triage.red_flags or [],
        "chief_complaint": triage.chief_complaint,
        "symptom_onset": triage.symptom_onset,
        "symptom_keywords": triage.symptom_keywords or [],
        "suspected_diseases": triage.suspected_diseases or [],
        "symptom_summary": triage.symptom_summary,
        "need_followup": bool(triage.need_followup),
    }


# 슬롯 선택 단계 재개 — 문진 완료·예약 미확정 세션이 다시 열렸을 때
# 서버에서 schedule 에이전트를 재실행하고 task_id만 클라이언트로 내려준다.
# (Shadow Triage 정책: 진단성 triage 데이터는 클라이언트로 보내지 않는다.)
@router.post("/sessions/{session_id}/resume-schedule")
async def resume_schedule(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다.")
    if session.emrid is None:
        raise HTTPException(status_code=400, detail="예약 가능한 상담이 아닙니다.")

    triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == session.emrid))
    triage = triage_row.scalar_one_or_none()
    if not triage:
        raise HTTPException(status_code=400, detail="문진 데이터가 없습니다. 처음부터 상담을 다시 진행해주세요.")

    pet_row = await db.execute(select(Pet).where(Pet.petid == session.petid))
    pet = pet_row.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    from app.crud.patient import build_patient_context
    from ai.router import _execute_agent

    patient_context_data = await build_patient_context(db, session.petid)
    pet_age = (date.today().year - pet.birth_date.year) if pet.birth_date else None
    pet_payload = {
        "name": pet.petname,
        "species": pet.species or "dog",
        "breed": pet.breed or "알 수 없음",
        "age": pet_age,
        "gender": pet.gender,
        "weight": float(pet.weight_kg) if pet.weight_kg else None,
    }
    collected_info = _triage_result_to_dict(triage)

    task_id = str(uuid.uuid4())
    _task_store[task_id] = {"status": TaskStatus.QUEUED, "step": ""}
    safe_create_task(
        _execute_agent(
            task_id,
            "schedule",
            {"pet": pet_payload, "triage_result": collected_info, "patient_context": patient_context_data},
            session.emrid,
            None,
            None,
        ),
        task_id=task_id,
        name="resume_schedule",
    )

    return {
        "code": 200,
        "result": {
            "schedule_task_id": task_id,
            "emrid": session.emrid,
            "triage_info": _guardian_safe_triage(collected_info),
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
