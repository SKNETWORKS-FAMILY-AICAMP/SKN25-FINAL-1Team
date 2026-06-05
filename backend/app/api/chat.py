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
from app.services.triage_kb import detect_red_flag, red_flag_trigger
from app.services import triage_engine as te
from ai.tasks import RUNNERS, _task_store, cleanup_task_after_ttl, safe_create_task, TaskStatus, PipelineState

import random
import re

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


# ── Decision tree walker 헬퍼 (Step 1/2) ────────────────────────────
# 매 질문 앞에 붙일 공감 문구 (연속 반복 회피용 회전). 무-LLM, 무지연.
_EMPATHY_OPENERS = [
    "걱정 많으셨겠어요.",
    "잘 알려주셨어요.",
    "도움이 되는 내용이에요.",
    "확인 도와드릴게요.",
    "차근차근 여쭤볼게요.",
]

# 단일 클릭 UX이므로 질문 끝의 "(해당하는 것 선택)/(해당 모두 선택)" 류 멀티 안내는 표시 안 함
_SELECT_HINT_RE = re.compile(r"\s*[\(（][^)）]*선택[^)）]*[\)）]\s*$")


def _q_text(text: str) -> str:
    """표시용 질문 텍스트 — 멀티선택 안내 괄호구문 제거."""
    return _SELECT_HINT_RE.sub("", text or "").strip()


def _load_walker_state(session) -> dict:
    """직전 어시스턴트 메시지의 meta로 현재 walker 상태를 복원.

    없으면(첫 턴) START_NODE로 시작.
    형태: {"node_id": str, "section": str|None, "answers": [pill dict, ...]}
    """
    for m in reversed(session.messages or []):
        if m.get("role") == "assistant" and isinstance(m.get("meta"), dict):
            meta = m["meta"]
            return {
                "node_id": meta.get("node_id", te.START_NODE),
                "section": meta.get("section"),
                "answers": list(meta.get("answers") or []),
            }
    return {"node_id": te.START_NODE, "section": None, "answers": []}


def _match_user_selections(node_id: str, text: str) -> list[dict]:
    """사용자 입력(멀티는 줄바꿈으로 join)을 현재 노드 pill에 매칭."""
    selected: list[dict] = []
    for seg in (text or "").split("\n"):
        pill = te.match_pill(node_id, seg)
        if pill and pill not in selected:
            selected.append(pill)
    return selected


async def _llm_classify_pills(node_id: str, user_text: str, species: str | None) -> list[dict]:
    """자유텍스트를 현재 노드 보기(pill) 중 의미가 맞는 것으로 LLM 분류(2c).

    결정론 walker의 자유텍스트 어댑터 — 매칭 pill dict 목록 반환(없으면 []).
    추측 금지(명백할 때만) → 분류 실패 시 빈 목록.
    """
    node = te.get_node(node_id)
    pills = te.visible_pills(node_id, species)
    if not node or not pills:
        return []

    options = "\n".join(f"- {p['value']}: {p['label']}" for p in pills)
    multi = node.get("type") == "multi"
    system = (
        "너는 반려동물 보호자의 한국어 발화를 아래 '보기' 중 의미가 일치하는 것으로 매칭하는 분류기야.\n"
        f"[질문] {node.get('text', '')}\n[보기]\n{options}\n\n"
        "사용자 발화에 해당하는 보기의 value만 JSON으로 반환해: {\"values\": [\"value\", ...]}\n"
        + ("의미상 해당하는 것을 모두 골라. " if multi else "가장 잘 맞는 하나만 골라. ")
        + "명백히 해당하는 보기가 없으면 {\"values\": []}. 억지 추측 금지."
    )
    try:
        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL or "gpt-4o",
            api_key=settings.OPENAI_API_KEY,
            temperature=0,
            timeout=20.0,
            max_retries=0,
            model_kwargs={"max_completion_tokens": 200, "response_format": {"type": "json_object"}},
        )
        resp = await llm.ainvoke(
            [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
            config={"run_name": "triage_classify", "callbacks": [get_langfuse_handler()]},
        )
        raw = resp.content if isinstance(resp.content, str) else "{}"
        values = (json.loads(raw) or {}).get("values") or []
    except Exception as e:
        logger.warning(f"[Triage] free-text 분류 실패 node={node_id}: {e}")
        return []

    by_val = {p["value"]: p for p in pills}
    matched = [by_val[v] for v in values if v in by_val]
    return matched if multi else matched[:1]


async def _freeform_reply(symptom: str, species: str | None) -> str:
    """응급 트리에 안 맞는 비응급 증상(피부·정기검진 등)에 대한 자연스러운 후속 응답.

    공감 + 관찰 기반 질문 1개를 LLM이 생성(진단명·응급표현 금지). 실패 시 기본 멘트.
    """
    animal = "고양이" if species == "cat" else "강아지"
    system = (
        f"너는 동물병원 AI 상담 도우미야. 보호자가 {animal} 증상으로 '{symptom}'라고 말했어.\n"
        "이건 당장 생명을 위협하는 응급은 아닌 일반 증상이야. 다음 규칙으로 답해:\n"
        "- 공감 한 문장 + 증상을 조금 더 파악하기 위한 자연스러운 질문 1개.\n"
        "- 보호자가 '관찰'로 답할 수 있는 쉬운 질문만(예: 언제부터, 가려워하는지, 크기 변화).\n"
        "- 병명 단정·'응급/생명위협' 같은 표현 금지. 따뜻하고 짧게(1~2문장).\n"
        "- 순수 한국어 텍스트만 출력(JSON 아님)."
    )
    try:
        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL or "gpt-4o",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.4,
            timeout=20.0,
            max_retries=0,
            model_kwargs={"max_completion_tokens": 200},
        )
        resp = await llm.ainvoke(
            [{"role": "system", "content": system}, {"role": "user", "content": symptom}],
            config={"run_name": "triage_freeform", "callbacks": [get_langfuse_handler()]},
        )
        text = (resp.content if isinstance(resp.content, str) else "").strip()
        return text or "걱정되시겠어요. 언제부터 그런 모습이 보였는지 조금 더 알려주실 수 있을까요?"
    except Exception as e:
        logger.warning(f"[Triage] freeform reply 실패: {e}")
        return "걱정되시겠어요. 언제부터 그런 모습이 보였는지 조금 더 알려주실 수 있을까요?"


def _freeform_collected_info(symptom: str, answer: str) -> dict:
    """비응급 freeform 완료용 collected_info(준긴급, Level 4)."""
    summary = symptom if not answer.strip() else f"{symptom} / {answer}"
    return {
        "is_triage_complete": True,
        "urgency_level": "준긴급",
        "urgency_level_num": 4,
        "vtl_basis": "freeform 비응급(응급 카테고리 미해당)",
        "red_flags": [],
        "is_initial_visit": True,
        "chief_complaint": symptom[:40],
        "symptom_keywords": [symptom[:20]],
        "suspected_diseases": [],
        "symptom_summary": summary[:200],
        "recommended_action": "진료 예약 권장",
        "need_followup": False,
        "followup_reason": None,
    }


async def _complete_and_schedule(
    db, session, collected_info: dict, pet_payload: dict, patient_context_data: dict,
) -> tuple[int, str]:
    """문진 완료 공통 처리 — TriageResult 저장 + Guardian + Schedule BG 실행.

    red flag 단축과 walker 종료 양쪽에서 재사용. (emrid, schedule_task_id) 반환.
    """
    keywords = collected_info.get("symptom_keywords") or []
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

    # 초기 증상 질문/pill을 decision tree(Q_INIT_SYMPTOM)에서 단일 출처로 내려준다.
    init_node = te.get_node(te.START_NODE) or {}
    species = pet.species or "dog"
    return {
        "code": 201,
        "result": {
            "session_id": session.id,
            "pet_name": pet.petname,
            "profile_image": pet.profile_image,
            "initial_message": _q_text(init_node.get("text", "어떤 증상 때문에 예약을 원하시나요?")),
            "initial_pills": te.pill_labels(te.START_NODE, species),
            "initial_multi": te.is_multi(te.START_NODE),
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
            # ── Decision tree walker (Step 1/2) — 결정론 주도, LLM은 분류만 ──
            species = pet.species or "dog"
            gender = pet.gender
            user_text = request.content or ""

            CHUNK = 10

            async def stream_msg(text: str):
                for i in range(0, len(text), CHUNK):
                    yield f"data: {json.dumps({'type': 'message', 'content': text[i:i + CHUNK]}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)

            def qr_event(nid: str) -> str:
                payload = {
                    "type": "quick_replies",
                    "options": te.pill_labels(nid, species),
                    "multi": te.is_multi(nid),
                }
                return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            done_event = f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

            # 현재 walker 상태 복원(직전 어시스턴트 메시지 meta)
            state = _load_walker_state(session)
            node_id = state["node_id"]

            # 1) Red flag 단축경로(결정론) — 매 턴 우선 체크
            det_hit = detect_red_flag(user_text)
            if det_hit:
                logger.warning("[Triage] RED FLAG hit session=%s id=%s (walker)", session.id, det_hit["id"])
                # 보호자에게는 '응급/생명위협' 표현을 쓰지 않고(guardian-safe) 자연스럽게
                # 마무리한다. 긴급도는 내부적으로만 RED로 처리되어 빠른 예약으로 연결된다.
                msg = "말씀해 주셔서 감사해요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요 🙏"
                collected_info = {
                    "is_triage_complete": True,
                    "urgency_level": "즉시",
                    "urgency_level_num": 1,
                    "vtl_basis": f"Red flag {det_hit['id']}: {det_hit['label']}",
                    "red_flags": [det_hit["id"]],
                    "is_initial_visit": True,
                    "chief_complaint": det_hit["label"],
                    "symptom_keywords": [det_hit["label"]],
                    "suspected_diseases": [],
                    "symptom_summary": det_hit["label"],
                    "recommended_action": "즉시 내원",
                    "need_followup": True,
                    "followup_reason": f"응급 red flag: {det_hit['label']}",
                }
                await add_message(db, session, "assistant", msg)
                async for c in stream_msg(msg):
                    yield c
                emrid, sched = await _complete_and_schedule(
                    db, session, collected_info, pet_payload, patient_context_data
                )
                yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(collected_info), 'emrid': emrid, 'schedule_task_id': sched}, ensure_ascii=False)}\n\n"
                yield done_event
                return

            # 1.5) FREEFORM(비응급) 후속 답변 → 비응급으로 즉시 완료
            if node_id == "FREEFORM":
                symptom = state.get("symptom") or user_text
                collected_info = _freeform_collected_info(symptom, user_text)
                msg = "증상 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요 🙏"
                await add_message(db, session, "assistant", msg)
                async for c in stream_msg(msg):
                    yield c
                emrid, sched = await _complete_and_schedule(
                    db, session, collected_info, pet_payload, patient_context_data
                )
                yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(collected_info), 'emrid': emrid, 'schedule_task_id': sched}, ensure_ascii=False)}\n\n"
                yield done_event
                return

            # 2) 사용자 입력 → 현재 노드 pill 매칭(멀티 지원)
            #    pill 클릭은 라벨 정확매칭, 자유텍스트는 LLM이 현재 노드 보기로 분류(2c).
            selected = _match_user_selections(node_id, user_text)
            if not selected and user_text.strip():
                selected = await _llm_classify_pills(node_id, user_text, species)
            if not selected:
                # START에서 응급 카테고리에 안 맞으면(피부·정기검진 등 비응급) 10개 보기를
                # 다시 쏟아내지 않고, 자연스럽게 알아듣고 부드러운 후속 질문 1개로 넘어간다.
                if node_id == te.START_NODE and user_text.strip():
                    followup = await _freeform_reply(user_text, species)
                    new_state = {"node_id": "FREEFORM", "section": "GENERAL",
                                 "answers": [], "symptom": user_text}
                    await add_message(db, session, "assistant", followup, meta=new_state)
                    async for c in stream_msg(followup):
                        yield c
                    yield done_event  # pill 없음 — 자유 입력 기대
                    return
                # 섹션 내 등 그 외: 현재 질문/pill 재안내(보기 2~4개)
                msg = "조금 더 구체적으로 말씀해 주시거나, 아래 보기 중에서 골라 주세요 🙏"
                await add_message(db, session, "assistant", msg, meta=state)
                async for c in stream_msg(msg):
                    yield c
                yield qr_event(node_id)
                yield done_event
                return

            # 3) 상태 갱신 — START_NODE 선택은 점수 0이라 answers에 누적하지 않음
            section = state.get("section")
            if node_id == te.START_NODE:
                section = selected[0].get("next_section") or selected[0].get("value")
                answers = list(state["answers"])
            else:
                answers = list(state["answers"]) + selected

            # 4) 다음 노드 결정
            next_node = te.advance(node_id, selected)

            if next_node is None:
                # 종료 → 결정론 scoring으로 collected_info 산출
                collected_info = te.to_collected_info(answers, species, section, gender)
                msg = "증상을 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요."
                await add_message(db, session, "assistant", msg)
                async for c in stream_msg(msg):
                    yield c
                emrid, sched = await _complete_and_schedule(
                    db, session, collected_info, pet_payload, patient_context_data
                )
                yield f"data: {json.dumps({'type': 'triage_complete', 'data': _guardian_safe_triage(collected_info), 'emrid': emrid, 'schedule_task_id': sched}, ensure_ascii=False)}\n\n"
                yield done_event
            else:
                # 다음 질문 제시(공감 문구 + JSON 질문 + JSON pill)
                q = te.get_node(next_node)
                msg = f"{random.choice(_EMPATHY_OPENERS)} {_q_text(q['text'])}"
                new_state = {"node_id": next_node, "section": section, "answers": answers}
                await add_message(db, session, "assistant", msg, meta=new_state)
                async for c in stream_msg(msg):
                    yield c
                yield qr_event(next_node)
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
