from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import asyncio
import logging
import uuid
import base64
from datetime import date
from langchain_openai import ChatOpenAI
from ai.observability import get_langfuse_handler
from app.db.session import get_db
from app.schemas.chat import ChatSessionCreate, ChatMessageRequest
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
from app.prompts.triage_prompt import _build_triage_system_prompt
from ai.tasks import RUNNERS, _task_store, cleanup_task_after_ttl, safe_create_task, TaskStatus, PipelineState

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# Shadow Triage / Zero-Liability:
# 보호자 프론트엔드로는 진단성 정보(응급도 라벨·red_flags·추측질환·VTL 근거 등)를
# 절대 내려보내지 않는다. 전체 triage 결과는 triage_resultDB에 저장되어 수의사만 열람한다.
# 클라이언트에는 예약 흐름 제어에 필요한 최소 필드만 전달한다.
_GUARDIAN_SAFE_FIELDS = ("is_triage_complete", "urgency_level_num", "need_followup", "symptom_keywords")


def _format_photo_analysis_for_prompt(analysis: dict | None) -> str:
    if not analysis:
        return ""

    lines = ["[첨부 사진 AI 분석 참고자료]"]
    visual = analysis.get("visual_observation")
    if isinstance(visual, dict):
        visible_changes = visual.get("visible_changes") or []
        if visible_changes:
            lines.append(f"- 사진 관찰: {', '.join(str(item) for item in visible_changes[:4])}")
        if visual.get("lesion_location"):
            lines.append(f"- 관찰 위치: {visual['lesion_location']}")
        if visual.get("question_focus"):
            lines.append(f"- 다음 질문 초점: {visual['question_focus']}")

    skin = analysis.get("skin")
    if isinstance(skin, dict):
        if "error" in skin:
            lines.append(f"- 피부 모델: 분석 실패({skin['error']})")
        else:
            skin_class = skin.get("top_class")
            lines.append(
                "- 피부 모델: "
                f"{skin.get('top_1') or '결과 없음'}; "
                f"상위 후보: {', '.join(skin.get('details') or [])}"
            )
            if skin_class and skin_class != "healthy":
                lines.append(
                    "- 답변 지침: 첫 문장에서 사진과 보조 분석상 피부 변화 가능성이 보인다고 짧게 언급한 뒤, "
                    "가려움·통증·크기 변화·진물/출혈 중 하나를 구체적으로 질문하세요."
                )

    eye = analysis.get("eye")
    if isinstance(eye, dict):
        if "error" in eye:
            lines.append(f"- 안구 모델: 분석 실패({eye['error']})")
        else:
            lines.append(
                "- 안구 모델: "
                f"{eye.get('top_1') or '결과 없음'}; "
                f"상위 후보: {', '.join(eye.get('details') or [])}"
            )

    lines.append(
        "- 위 결과는 사진 기반 보조 분류이며, 보호자에게 확정 진단처럼 말하지 말고 "
        "문진 질문과 내원 필요성 판단의 참고자료로만 사용하세요."
    )
    return "\n".join(lines)


def _message_content_for_openai(message: dict) -> str:
    content = message.get("content") or ""
    photo_analysis = _format_photo_analysis_for_prompt(message.get("photo_analysis"))
    if photo_analysis:
        return f"{content}\n\n{photo_analysis}"
    return content


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


def _message_for_openai(message: dict) -> dict:
    role = message["role"]
    text_content = _message_content_for_openai(message)
    image_url = message.get("image_url")

    if role == "user" and image_url:
        try:
            return {
                "role": role,
                "content": [
                    {"type": "text", "text": text_content},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _image_data_url_from_s3_url(image_url),
                            "detail": "high",
                        },
                    },
                ],
            }
        except Exception as exc:
            logger.warning("[Vision/Chat] OpenAI image payload failed image_url=%s: %s", image_url, exc)

    return {"role": role, "content": text_content}


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


async def _run_schedule_background(
    task_id: str,
    emrid: int,
    pet_payload: dict,
    triage_info: dict,
    patient_context: dict,
) -> None:
    """triage_complete 직후 asyncio.create_task로 실행되는 Schedule Agent 백그라운드 러너."""
    logger.info(f"[Schedule BG] start task_id={task_id} emrid={emrid}")
    _task_store[task_id] = {"status": "running", "step": "예약 슬롯 계산 중..."}

    def update_step(step: str) -> None:
        _task_store[task_id]["step"] = step

    try:
        payload = {
            "pet": pet_payload,
            "triage_info": triage_info,
            "triage_result": triage_info,
            "patient_context": patient_context,
            "existing_bookings": [],
        }
        result = await RUNNERS["schedule"](payload, update_step, emrid, None)
        _task_store[task_id] = {"status": "done", "result": result}
        logger.info(f"[Schedule BG] done task_id={task_id} slot_window={result.get('slot_window')}")
    except Exception as exc:
        logger.error(f"[Schedule BG] failed task_id={task_id}: {exc}", exc_info=True)
        _task_store[task_id] = {"status": "error", "detail": str(exc)}
    finally:
        safe_create_task(
            cleanup_task_after_ttl(task_id),
            name=f"cleanup:{task_id}",
        )


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

    session = await get_chat_session(db, session_id, current_user.userid)
    if not session:
        raise HTTPException(status_code=404, detail="상담 세션을 찾을 수 없습니다.")

    pet_result = await db.execute(select(Pet).where(Pet.petid == session.petid))
    pet = pet_result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    photo_analysis = None
    if request.image_url:
        photo_analysis = await _analyze_chat_photo(request.image_url, request.content)
        visual_observation = await _describe_chat_photo(request.image_url, request.content)
        if visual_observation:
            photo_analysis = photo_analysis or {}
            photo_analysis["visual_observation"] = visual_observation

    await add_message(db, session, "user", request.content, request.image_url, photo_analysis=photo_analysis)

    from app.crud.patient import build_patient_context
    
    patient_context_data = await build_patient_context(db, session.petid)
    emr_history = patient_context_data["patient_context"]["emr_history"] # For backward compatibility with Triage prompt until we update it

    openai_messages = [
        _message_for_openai(m)
        for m in (session.messages or [])
        if m.get("role") in ("user", "assistant") and _message_content_for_openai(m)
    ]

    turn_count = sum(1 for m in openai_messages if m["role"] == "assistant")
    force_complete = turn_count >= 4

    system_prompt = _build_triage_system_prompt(pet, patient_context=patient_context_data, force_complete=force_complete)

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
            # GPT-5 계열은 max_tokens 미지원(max_completion_tokens 사용) + 추론 토큰을
            # 출력 예산에서 함께 소모하므로 넉넉히 둔다. gpt-4o 계열도 동일 파라미터 허용.
            # LangChain 구버전의 자동 max_tokens 매핑을 우회하려 model_kwargs 로 직접 전달.
            llm = ChatOpenAI(
                model=settings.OPENAI_MODEL or "gpt-4o",
                api_key=settings.OPENAI_API_KEY,
                temperature=0.3,
                timeout=45.0,
                max_retries=0,
                model_kwargs={"max_completion_tokens": 2000, "response_format": {"type": "json_object"}},
            )

            # JSON 모드로 전체 응답 수신 — timeout(45s) + 1회 재시도로 일시 오류에 대응.
            # 두 번 다 실패하면 아래 except가 error 이벤트로 graceful 종료.
            response = None
            for attempt in range(1, 3):
                try:
                    response = await llm.ainvoke(
                        [{"role": "system", "content": system_prompt}] + openai_messages,
                        config={"run_name": "triage", "callbacks": [get_langfuse_handler()]},
                    )
                    break
                except Exception as oa_exc:
                    logger.warning(f"[Triage] LLM 호출 실패 (attempt {attempt}/2): {oa_exc}")
                    if attempt >= 2:
                        raise
                    await asyncio.sleep(0.5)

            raw = response.content if isinstance(response.content, str) else ""

            # JSON 파싱 (마크다운 래핑 제거)
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                parsed = {"message": raw, "suggestions": [], "collected_info": None}

            message_text = parsed.get("message", "")
            suggestions = parsed.get("suggestions") or []
            collected_info = parsed.get("collected_info")

            # suggestions 정제 — 보호자의 '답변' 후보만 노출한다.
            # 모델이 가끔 질문형("최근에 구토를 했나요?")을 선택지로 내놓는데,
            # 물음표로 끝나면 질문이므로 제거한다. (결정론적 — 모델 품질과 무관하게 보장)
            suggestions = [
                s.strip() for s in suggestions
                if isinstance(s, str) and s.strip() and not s.strip().endswith("?")
            ][:3]
            # 문진이 끝나지 않은 대화 진행 중에는 답변형 pill이 항상 떠야 한다.
            # 모델이 전부 질문형을 내놓아 비게 되면 기본 답변 선택지로 대체.
            is_complete = bool(collected_info and collected_info.get("is_triage_complete"))
            if not is_complete and not suggestions:
                suggestions = ["네, 그래요", "아니요, 괜찮아요", "잘 모르겠어요"]

            # AI 응답 DB 저장
            await add_message(db, session, "assistant", message_text)

            # message 텍스트를 청크로 스트리밍
            chunk_size = 10
            for i in range(0, len(message_text), chunk_size):
                chunk = message_text[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'message', 'content': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)

            # 에이전트가 제시한 선택지 전송
            if suggestions:
                yield f"data: {json.dumps({'type': 'quick_replies', 'options': suggestions}, ensure_ascii=False)}\n\n"

            # 문진 완료 처리
            if collected_info and collected_info.get("is_triage_complete"):
                keywords = collected_info.get("symptom_keywords") or []
                await update_session_complete(db, session, keywords)

                # ① Guardian 생성 → emrid 확보
                guardian = await create_triage_guardian(db, session.petid)
                emrid = guardian.emrid

                # ② ChatHistory.emrid 업데이트 (NULL → emrid, 1회만)
                await update_session_emrid(db, session, emrid)

                # ③ TriageResult INSERT (공용 빌더로 매핑 단일화 — crud/triage.py)
                try:
                    db.add(build_triage_result(emrid, collected_info))
                    await db.commit()
                    logger.info(f"[TriageResult] saved emrid={emrid}")
                    # ③-a Guardian category_id를 실제 증상 기반으로 업데이트
                    await update_guardian_category(
                        db,
                        emrid,
                        symptom_keywords=collected_info.get("symptom_keywords") or [],
                        chief_complaint=collected_info.get("chief_complaint") or "",
                    )
                    logger.info(f"[TriageResult] guardian category updated emrid={emrid}")
                except Exception as e:
                    await db.rollback()
                    logger.error(f"[TriageResult] save failed emrid={emrid}: {e}")

                # ④ Schedule Agent 백그라운드 실행
                schedule_task_id = str(uuid.uuid4())
                _task_store[schedule_task_id] = {"status": TaskStatus.QUEUED, "step": ""}
                logger.info(
                    "[Schedule BG] queued pipeline_state=%s task_id=%s emrid=%s",
                    PipelineState.SCHEDULE_PENDING, schedule_task_id, emrid,
                )
                safe_create_task(
                    _run_schedule_background(schedule_task_id, emrid, pet_payload, collected_info, patient_context_data),
                    task_id=schedule_task_id,
                    name="schedule_bg",
                )

                yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(collected_info), 'emrid': emrid, 'schedule_task_id': schedule_task_id}, ensure_ascii=False)}\n\n"
            else:
                if collected_info:
                    yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(collected_info)}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

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
    emrid = session.emrid
    if emrid is not None:
        from datetime import datetime, timezone
        triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
        triage = triage_row.scalar_one_or_none()
        schedule_row = await db.execute(
            select(Schedule).where(Schedule.emrid == emrid, Schedule.deleted_at.is_(None))
        )
        schedule = schedule_row.scalar_one_or_none()
        need_followup = bool(triage and triage.urgency_level_num is not None and triage.urgency_level_num <= 2)
        appointment_not_passed = True
        if schedule and schedule.confirmed_time:
            confirmed = schedule.confirmed_time
            if confirmed.tzinfo is None:
                confirmed = confirmed.replace(tzinfo=timezone.utc)
            appointment_not_passed = datetime.now(timezone.utc) <= confirmed
        can_followup = bool(need_followup and schedule and schedule.status != "COMPLETED" and appointment_not_passed)

    return {
        "code": 200,
        "result": {
            "session_id": session.id,
            "pet_id": session.petid,
            "emrid": emrid,
            "messages": session.messages or [],
            "keywords": session.keywords or [],
            "is_complete": session.is_complete,
            "can_followup": can_followup,
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
