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
from ai.agents.base import call_openai
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
from ai.triage.kb import detect_red_flag, red_flag_trigger
from ai.triage import engine as te
from ai.triage.rag import TriageRagMatch, search_similar_triage_cases
from ai.tasks import _task_store, cleanup_task_after_ttl, safe_create_task, TaskStatus, PipelineState

import random
import re

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# Shadow Triage / Zero-Liability:
# 보호자 프론트엔드로는 진단성 정보(응급도 라벨·red_flags·추측질환·VTL 근거 등)를
# 절대 내려보내지 않는다. 전체 triage 결과는 triage_resultDB에 저장되어 수의사만 열람한다.
# 클라이언트에는 예약 흐름 제어에 필요한 최소 필드만 전달한다.
_GUARDIAN_SAFE_FIELDS = ("is_triage_complete", "urgency_level_num", "need_followup", "symptom_keywords")
_TRIAGE_RAG_TOP_K = 3
_TRIAGE_RAG_MIN_SIMILARITY = 0.60
_FREEFORM_MIN_USER_TURNS = 3
_FREEFORM_MAX_USER_TURNS = 5


def _content_text(content: str | None) -> str:
    return " ".join((content or "").split())


def _session_user_messages(session) -> list[str]:
    return [
        _content_text(m.get("content"))
        for m in (session.messages or [])
        if m.get("role") == "user" and _content_text(m.get("content"))
    ]


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
                "symptom": meta.get("symptom"),
                "rag_context": list(meta.get("rag_context") or []),
                "freeform_turns": meta.get("freeform_turns"),
            }
    return {
        "node_id": te.START_NODE,
        "section": None,
        "answers": [],
        "symptom": None,
        "rag_context": [],
        "freeform_turns": None,
    }


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


def _heuristic_classify_pills(node_id: str, user_text: str, species: str | None) -> list[dict]:
    """LLM 분류 실패 시 자연어 답변을 보수적으로 pill에 매칭한다.

    사용자가 pill을 누르지 않고 말로 답해도 같은 질문을 반복하지 않기 위한 안전망이다.
    명확한 표현만 처리하고, 애매하면 빈 목록을 반환한다.
    """
    text = (user_text or "").replace(" ", "")
    if not text:
        return []

    pills = te.visible_pills(node_id, species)
    by_value = {p.get("value"): p for p in pills}
    values: list[str] = []

    # START 라우터 안전망: LLM 분류가 놓쳐도 '트리가 커버하는' 증상이 freeform으로
    # 새지 않게 키워드로 섹션을 잡는다. 피부·안구 등 off-tree 키워드는 일부러 넣지
    # 않아(→ freeform 유지) 주제 커버리지 기준 라우팅을 지킨다.
    if node_id == te.START_NODE:
        section_keywords = (
            ("RESPIRATORY", ("숨", "호흡", "헐떡", "기침", "쌕쌕", "그르렁", "숨가", "개구호흡", "숨소리")),
            ("SEIZURE", ("발작", "경련", "바들바들", "부들부들", "거품물", "버둥")),
            ("COLLAPSE", ("쓰러", "기절", "실신", "축늘어", "의식없", "의식이없")),
            ("CARDIAC", ("심장", "심부전", "부정맥", "맥박", "심박")),
            ("UNABLE_TO_WALK", ("못걷", "못걸", "마비", "절뚝", "절어", "기립", "주저앉", "뒷다리", "일어서지")),
            ("BLEEDING", ("출혈", "피가나", "피를흘", "피흘", "코피", "피가멈")),
            ("GI", ("토해", "토하", "토했", "구토", "설사", "혈변", "흑변", "복부팽", "배가부", "배부풀", "이물", "삼켰", "삼킨")),
            ("TRAUMA", ("다쳤", "다침", "외상", "골절", "부러", "교통사고", "물렸", "찢어", "베였", "부딪")),
            ("UROGENITAL", ("소변", "오줌", "배뇨", "혈뇨", "방광", "요도", "변비", "지렸")),
        )
        for sec, kws in section_keywords:
            if sec in by_value and any(kw in text for kw in kws):
                return [by_value[sec]]  # START는 selected[0]만 사용 → 단일 섹션 반환
        # 전신 비특이 증상은 다른 섹션이 하나도 안 잡혔을 때만 GENERAL로
        if "GENERAL" in by_value and any(
            kw in text for kw in ("기운없", "기운이없", "기력", "축처", "안먹", "밥안", "식욕", "무기력", "못먹")
        ):
            return [by_value["GENERAL"]]
        return []

    def choose(value: str) -> None:
        if value in by_value and value not in values:
            values.append(value)

    if node_id == "Q_RESP_SOUND":
        if any(token in text for token in ("계속", "자주", "많이", "심해", "하루종일", "잦")):
            choose("persistent")
        elif any(token in text for token in ("가끔", "조금", "몇번", "한두번")):
            choose("occasional")

    elif node_id in {"Q_RESP_TIMING", "Q_GI_TIMING"}:
        if any(token in text for token in ("수분", "1시간", "방금", "지금막", "갑자기지금")):
            choose("abrupt")
        elif any(token in text for token in ("오늘", "오늘부터", "갑자기", "어제는괜찮", "하루안")):
            choose("rapid" if "rapid" in by_value else "abrupt")
        elif any(token in text for token in ("2일", "3일", "이틀", "삼일", "며칠")):
            choose("acute")
        elif any(token in text for token in ("1주", "일주", "오래", "계속그랬")):
            choose("recent")

    elif node_id == "Q_GI_01":
        if any(token in text for token in ("배가부", "복부팽", "배부풀", "배가커")):
            choose("acute_bloat")
        if any(token in text for token in ("구토", "토해", "토하", "토를", "토했")):
            choose("vomiting")
        if "설사" in text:
            choose("diarrhea")
        if any(token in text for token in ("검은변", "검정변", "피섞", "혈변", "피똥", "흑변")):
            choose("melena")
        if any(token in text for token in ("이물", "삼켰", "삼킨", "먹었는데", "먹은것")):
            choose("foreign_body")
        if any(token in text for token in ("독성", "초콜릿", "약을먹", "독극", "중독")):
            choose("toxin")

    elif node_id == "Q_GI_02":
        if any(token in text for token in ("계속", "반복", "자주", "많이", "멈추지", "여러번")):
            choose("persistent")
        elif any(token in text for token in ("이물", "삼킨", "삼켰")) and any(token in text for token in ("24시간", "하루", "어제")):
            choose("fb_over_24h")
        elif any(token in text for token in ("피", "혈", "빨갛", "검은")):
            choose("blood")
        elif any(token in text for token in ("몇번", "한두번", "지금은괜찮", "괜찮아", "가끔")):
            choose("mild")

    elif node_id == "Q_RESP_02":
        if any(token in text for token in ("쌕쌕", "그르렁", "소리", "가래", "켁켁")):
            choose("stridor")
        elif any(token in text for token in ("소리없", "조용", "숨만가빠")):
            choose("silent")
        elif any(token in text for token in ("모르", "잘몰")):
            choose("unknown")

    elif node_id == "Q_RESP_03":
        if any(token in text for token in ("부풀", "공기", "피부아래")):
            choose("subcutaneous_emphysema")
        if any(token in text for token in ("불독", "퍼그", "시추", "납작", "단두")):
            choose("brachycephalic")
        if any(token in text for token in ("심장", "심부전", "심장병")):
            choose("cardiac_history")
        if any(token in text for token in ("연기", "독가스", "가스")):
            choose("toxin_inhalation")
        if not values and any(token in text for token in ("없", "아니", "해당없", "괜찮")):
            choose("none")

    matched = [by_value[value] for value in values if value in by_value]
    if te.is_multi(node_id):
        return matched
    return matched[:1]


def _auto_answer_next_node(next_node: str | None, user_text: str, species: str | None) -> tuple[list[dict], str | None]:
    """현재 발화가 다음 질문의 답까지 포함하면 다음 노드를 자동으로 한 칸 더 진행한다."""
    if not next_node:
        return [], next_node
    node = te.get_node(next_node) or {}
    if node.get("type") == "multi":
        return [], next_node
    selected = _heuristic_classify_pills(next_node, user_text, species)
    if not selected:
        return [], next_node
    return selected, te.advance(next_node, selected)


def _fallback_free_text_selection(node_id: str, user_text: str, species: str | None) -> list[dict]:
    """보기 매칭이 끝까지 실패해도 같은 질문을 반복하지 않기 위한 자유답변 fallback."""
    text = _content_text(user_text)
    if not text or node_id == te.START_NODE:
        return []

    node = te.get_node(node_id) or {}
    pills = te.visible_pills(node_id, species)
    if not node or not pills:
        return []

    node_next = node.get("next")
    base = {
        "label": text[:120],
        "value": "free_text",
        "urgency_score": 0,
        "keywords": [],
        "free_text": True,
    }

    if node.get("type") == "multi":
        if node_next:
            return [{**base, "next": node_next}]
        return [base]

    preferred = next((p for p in pills if p.get("value") == "unknown"), None)
    if not preferred:
        forward = [p for p in pills if p.get("next") and not p.get("red_flag")]
        preferred = sorted(forward, key=lambda p: p.get("urgency_score") or 0)[0] if forward else None

    if preferred:
        return [{
            **base,
            "value": f"free_text:{preferred.get('value')}",
            "urgency_score": preferred.get("urgency_score") or 0,
            "urgency_modifier": preferred.get("urgency_modifier") or 0,
            "keywords": preferred.get("keywords") or [],
            "next": preferred.get("next") or node_next,
            "fallback_value": preferred.get("value"),
        }]

    if node_next:
        return [{**base, "next": node_next}]
    return [base]


def _rag_match_to_meta(match: TriageRagMatch) -> dict:
    return {
        "source_file": match.source_file,
        "department": match.department,
        "disease": match.disease,
        "life_cycle": match.life_cycle,
        "input_text": match.input_text,
        "output_text": match.output_text,
        "distance": match.distance,
        "similarity": match.similarity,
    }


def _usable_rag_context(matches: list[TriageRagMatch]) -> list[dict]:
    return [
        _rag_match_to_meta(m)
        for m in matches
        if m.similarity >= _TRIAGE_RAG_MIN_SIMILARITY
    ]


async def _search_triage_rag_context(db: AsyncSession, query: str) -> list[dict]:
    """자유 발화 보조용 RAG context.

    실패해도 triage flow를 막지 않는다. RAG는 판단 주체가 아니라 보조 힌트다.
    """
    if not (query or "").strip():
        return []
    try:
        matches = await search_similar_triage_cases(db, query, top_k=_TRIAGE_RAG_TOP_K)
        context = _usable_rag_context(matches)
        if matches:
            logger.info(
                "[TriageRAG] query=%r top_similarity=%.4f usable=%d/%d",
                query[:80],
                matches[0].similarity,
                len(context),
                len(matches),
            )
        return context
    except Exception as exc:
        logger.warning("[TriageRAG] search skipped: %s", exc)
        return []


def _format_rag_context_for_prompt(rag_context: list[dict]) -> str:
    if not rag_context:
        return ""

    lines = ["[유사 상담 사례 참고자료]"]
    for idx, item in enumerate(rag_context[:_TRIAGE_RAG_TOP_K], start=1):
        lines.append(
            f"{idx}. 유사도 {item.get('similarity', 0):.2f} / "
            f"진료과 {item.get('department') or '미상'} / "
            f"질환 {item.get('disease') or '미상'}"
        )
        lines.append(f"- 유사 질문: {str(item.get('input_text') or '')[:240]}")
        lines.append(f"- 사례 답변 요지: {str(item.get('output_text') or '')[:300]}")

    lines.append(
        "위 자료는 확정 진단이 아니라 다음 질문을 더 잘 고르기 위한 참고자료입니다. "
        "보호자에게 병명을 단정하지 마세요."
    )
    return "\n".join(lines)


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _content_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _entry_selections_from_text(section: str | None, species: str | None, text: str) -> tuple[str | None, list[dict]]:
    """START에서 자연어가 이미 섹션 첫 질문의 답을 포함하면 해당 pill을 선반영한다."""
    normalized = (text or "").replace(" ", "")
    if section != "GI" or not normalized:
        return None, []

    entry_node = te.advance(te.START_NODE, [{"value": section, "next_section": section}])
    if not entry_node:
        return None, []

    wanted_values: list[str] = []
    if any(token in normalized for token in ("배가부", "복부팽", "배부풀", "배가커")):
        wanted_values.append("acute_bloat")
    if any(token in normalized for token in ("구토", "토해", "토하", "토를", "토했")):
        wanted_values.append("vomiting")
    if "설사" in normalized:
        wanted_values.append("diarrhea")
    if any(token in normalized for token in ("검은변", "검정변", "피섞", "혈변", "피똥", "흑변")):
        wanted_values.append("melena")
    if any(token in normalized for token in ("이물", "삼켰", "삼킨", "먹었는데", "먹은것")):
        wanted_values.append("foreign_body")
    if any(token in normalized for token in ("독성", "초콜릿", "약을먹", "독극", "중독")):
        wanted_values.append("toxin")

    if not wanted_values:
        return None, []

    pills = te.visible_pills(entry_node, species)
    selected: list[dict] = []
    for value in wanted_values:
        for pill in pills:
            if pill.get("value") == value and pill not in selected:
                selected.append(pill)
                break
    return entry_node, selected


_FREEFORM_DEFAULT_REPLY = "걱정되시겠어요. 언제부터 그런 모습이 보였는지 조금 더 알려주실 수 있을까요?"
_FREEFORM_DEFAULT_CHIPS = ["오늘 처음 보였어요", "며칠 전부터 그랬어요", "잘 모르겠어요"]


async def _freeform_reply(
    symptom: str,
    species: str | None,
    rag_context: list[dict] | None = None,
    conversation: list[str] | None = None,
) -> tuple[str, list[str]]:
    """비응급 증상(피부·정기검진 등) 후속 응답을 LLM이 생성한다.

    공감 + 관찰 기반 질문 1개와, 그 질문에 바로 고를 수 있는 보기 3개를 한 번에 만든다
    (질문 초점·보기 하드코딩 제거). (질문문, 보기목록) 반환. 실패 시 기본값.
    """
    animal = "고양이" if species == "cat" else "강아지"
    rag_prompt = _format_rag_context_for_prompt(rag_context or [])
    asked = _dedupe_texts(conversation or [])
    asked_block = ("이미 나눈 대화: " + " / ".join(asked[-6:]) + "\n") if asked else ""
    system = (
        f"너는 동물병원 AI 상담 도우미야. 보호자가 {animal} 증상으로 '{symptom}'라고 말했어.\n"
        f"{asked_block}"
        "당장 생명을 위협하는 응급은 아닌 일반 증상이야. 다음 규칙으로 JSON을 만들어:\n"
        "- reply: 공감 한 문장 + 증상을 더 파악하기 위한 자연스러운 질문 1개. "
        "보호자가 '관찰'로 답할 수 있는 쉬운 질문만(예: 언제부터, 가려워하는지, 크기 변화).\n"
        "- quick_replies: 그 질문에 보호자가 바로 고를 수 있는 짧은 보기 3개.\n"
        "- 유사 상담 사례가 있으면 그 방향의 핵심 확인을 우선하되 병명은 단정하지 마.\n"
        "- 이미 나눈 대화와 같은 질문 반복 금지. 병명 단정·'응급/생명위협' 표현 금지. 따뜻하고 짧게.\n"
        + (f"\n{rag_prompt}\n" if rag_prompt else "")
        + 'JSON만 출력: {"reply":"...","quick_replies":["...","...","..."]}'
    )
    try:
        result = await call_openai(
            [{"role": "user", "content": symptom}],
            system,
            max_tokens=300,
            agent="triage_freeform",
        )
        if isinstance(result, dict):
            text = str(result.get("reply") or "").strip() or _FREEFORM_DEFAULT_REPLY
            chips = [str(c).strip() for c in (result.get("quick_replies") or []) if str(c).strip()][:3]
            return text, (chips or _FREEFORM_DEFAULT_CHIPS)
    except Exception as e:
        logger.warning(f"[Triage] freeform reply 실패: {e}")
    return _FREEFORM_DEFAULT_REPLY, _FREEFORM_DEFAULT_CHIPS


_OFFTOPIC_REDIRECT = (
    "저는 반려동물의 증상·건강 상담을 도와드리는 챗봇이에요. 🐾 "
    "지금 어떤 증상이 있거나 걱정되는 부분을 알려주시면 도와드릴게요."
)


async def _is_offtopic(text: str, species: str | None) -> bool:
    """반려동물 건강/증상과 무관한 발화(일반 지식·코딩·잡담 등)인지 LLM으로 판별.

    실패 시 False(보수적으로 진행 — 정상 문진을 막지 않는다).
    """
    text = (text or "").strip()
    if not text:
        return False
    system = (
        "너는 동물병원 '증상 상담 챗봇'의 입력 주제 필터야. 사용자 메시지가 "
        "반려동물의 건강·증상·상태·행동·복약·진료/예약과 조금이라도 관련 있으면 related, "
        "그 외(일반 상식, 프로그래밍/코딩, 수학, 시사, 사람 이야기, 잡담 등)면 unrelated 로 분류해. "
        "증상이 모호하거나 짧아도 동물 건강과 관련될 여지가 있으면 related 로 둬.\n"
        'JSON만 출력: {"topic": "related"} 또는 {"topic": "unrelated"}'
    )
    try:
        result = await call_openai(
            [{"role": "user", "content": text[:500]}],
            system,
            max_tokens=20,
            agent="triage_topic_guard",
        )
        if isinstance(result, dict):
            return str(result.get("topic") or "").strip().lower() == "unrelated"
    except Exception as e:
        logger.warning(f"[Triage] offtopic 판별 실패: {e}")
    return False


_FREEFORM_SIGNAL_KEYS = tuple(te.FREEFORM_SIGNAL_SCORES.keys())


def _format_rag_for_freeform(rag_context: list[dict] | None) -> str:
    items = rag_context or []
    if not items:
        return ""
    lines = ["참고 유사 상담사례(진단 단정 금지, 표현 참고용):"]
    for item in items[:3]:
        out = " ".join(str(item.get("output_text") or "").split())[:120]
        lines.append(f"- [{item.get('department')}/{item.get('disease')}] {out}")
    return "\n".join(lines)


def _empty_freeform_analysis() -> dict:
    return {
        "signals": {k: False for k in _FREEFORM_SIGNAL_KEYS},
        "chief_complaint": "",
        "symptom_keywords": [],
        "suspected_diseases": [],
        "symptom_summary": "",
    }


async def _llm_freeform_analysis(
    symptom: str,
    user_messages: list[str],
    species: str | None,
    rag_context: list[dict] | None = None,
) -> dict:
    """freeform 대화를 단일 LLM 호출로 분석한다(키워드 하드코딩 대체).

    반환: signals(5 bool) + chief_complaint + symptom_keywords + suspected_diseases
    + symptom_summary. signals는 te.compute_urgency로 점수화되어 응급도를 산출한다(A+B).
    실패하면 빈 분석(보수적으로 GREEN; 실제 응급은 상위 red-flag 감지가 처리).
    """
    convo = " / ".join(_dedupe_texts([symptom, *(user_messages or [])]))[:1000]
    animal = "고양이" if species == "cat" else "강아지"
    rag_block = _format_rag_for_freeform(rag_context)
    system = (
        f"너는 동물병원 트리아지 보조야. 보호자가 {animal} 증상을 다음처럼 설명했어:\n"
        f'"{convo}"\n\n'
        + (rag_block + "\n\n" if rag_block else "")
        + "대화를 바탕으로 아래 JSON을 채워. 대화에 없는 증상 추가·과장·진단 단정 금지(불확실하면 비워).\n"
        "- signals: 각 항목이 대화에 명확히 드러나면 true, 아니면 false\n"
        "    systemic_signs(발열·식욕저하·기력저하 등 전신증상), rapid_worsening(급격히 악화/번짐),\n"
        "    severe_pain(심한 통증), active_bleeding(출혈·궤양·진물), prolonged(수일 이상 지속)\n"
        "- chief_complaint: 주요 증상 한 줄(짧게)\n"
        "- symptom_keywords: 핵심 증상 키워드 2~5개(한국어)\n"
        "- suspected_diseases: 가능성 있는 질환 0~3개(불확실하면 빈 배열, 단정 금지)\n"
        "- symptom_summary: SOAP의 S에 해당하는 '한 줄' 요약. 짧은 한 문장으로, 반드시 "
        "'~이다/~한다/~보인다' 같은 평서형 종결로 끝낼 것(명사 나열·존댓말 금지). "
        "예: '오른쪽 귀를 자주 긁는 피부 증상이다.'\n\n"
        'JSON만 출력: {"signals":{"systemic_signs":false,"rapid_worsening":false,'
        '"severe_pain":false,"active_bleeding":false,"prolonged":false},'
        '"chief_complaint":"","symptom_keywords":[],"suspected_diseases":[],"symptom_summary":""}'
    )
    try:
        result = await call_openai(
            [{"role": "user", "content": convo}],
            system,
            max_tokens=400,
            agent="triage_freeform_analysis",
        )
        if isinstance(result, dict):
            sig = result.get("signals") or {}

            def _clean_list(values, limit):
                return [str(v).strip() for v in (values or []) if str(v).strip()][:limit]

            return {
                "signals": {k: bool(sig.get(k)) for k in _FREEFORM_SIGNAL_KEYS},
                "chief_complaint": str(result.get("chief_complaint") or "").strip(),
                "symptom_keywords": _clean_list(result.get("symptom_keywords"), 5),
                "suspected_diseases": _clean_list(result.get("suspected_diseases"), 3),
                "symptom_summary": str(result.get("symptom_summary") or "").strip(),
            }
    except Exception as e:
        logger.warning(f"[Triage] freeform 분석 실패: {e}")
    return _empty_freeform_analysis()


def _freeform_collected_info(
    symptom: str,
    rag_context: list[dict] | None = None,
    urgency: dict | None = None,
    analysis: dict | None = None,
) -> dict:
    """비응급 freeform 완료용 collected_info.

    analysis는 _llm_freeform_analysis 결과(키워드·의심질환·요약). urgency는 (A+B)
    심각도 점수 결과. 둘 다 미지정 시 보수적 기본값(GREEN, 빈 분석).
    """
    u = urgency or {"urgency_level": "일반", "urgency_level_num": 4,
                    "urgency": "GREEN", "total_score": 0}
    analysis = analysis or _empty_freeform_analysis()
    rag_context = rag_context or []
    rag_basis = ""
    if rag_context:
        top = rag_context[0]
        rag_basis = (
            f" / rag top={top.get('department')}/{top.get('disease')} "
            f"sim={float(top.get('similarity') or 0):.2f}"
        )

    keywords = analysis.get("symptom_keywords") or []
    # 의심질환: LLM 분석 우선, RAG 유사사례 질환으로 보강
    diseases = list(analysis.get("suspected_diseases") or [])
    for item in rag_context:
        disease = (item.get("disease") or "").strip()
        if disease and disease != "기타" and disease not in diseases:
            diseases.append(disease)
    summary = analysis.get("symptom_summary") or _content_text(symptom)[:300]
    chief = analysis.get("chief_complaint") or (keywords[0] if keywords else _content_text(symptom)[:40])

    num = u["urgency_level_num"]
    return {
        "is_triage_complete": True,
        "urgency_level": u["urgency_level"],
        "urgency_level_num": num,
        "vtl_basis": f"freeform score={u.get('total_score', 0)} → {u.get('urgency', 'GREEN')}{rag_basis}",
        "red_flags": [],
        "is_initial_visit": True,
        "chief_complaint": chief,
        "symptom_keywords": keywords or [chief],
        "suspected_diseases": diseases[:3],
        "symptom_summary": summary,
        "recommended_action": "진료 예약 권장",
        "need_followup": num <= 2,
        "followup_reason": (f"응급도 {u['urgency_level']}" if num <= 2 else None),
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

    # 요약 노드에 넘길 전체 대화(보호자+챗봇)
    session_messages = [
        {"role": m.get("role"), "content": _content_text(m.get("content"))}
        for m in (session.messages or [])
        if m.get("role") in ("user", "assistant") and _content_text(m.get("content"))
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

            # 1) Red flag 단축경로(결정론) — 매 턴 우선 체크.
            #    단, 현재 노드 pill을 '그대로 클릭'한 경우엔 walker가 처리하도록 단축을 건너뛴다.
            #    walker의 to_collected_info가 명사형 키워드·의심질환·평서형 요약을 제대로 채우기 때문.
            #    (자유 텍스트 응급 표현은 그대로 detect_red_flag가 잡는다.)
            _clicked_pill = bool(node_id != te.START_NODE and _match_user_selections(node_id, user_text))
            det_hit = None if _clicked_pill else detect_red_flag(user_text)
            if det_hit:
                logger.warning("[Triage] RED FLAG hit session=%s id=%s (walker)", session.id, det_hit["id"])
                # 보호자에게는 '응급/생명위협' 표현을 쓰지 않고(guardian-safe) 자연스럽게
                # 마무리한다. 긴급도는 내부적으로만 RED로 처리되어 빠른 예약으로 연결된다.
                msg = "말씀해 주셔서 감사해요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요 🙏"
                # 명사형 주증상(chief)·의심질환(suspected)은 KB red flag에 정의 — 없으면 라벨 폴백.
                rf_chief = det_hit.get("chief") or det_hit["label"]
                rf_suspected = det_hit.get("suspected") or []
                collected_info = {
                    "is_triage_complete": True,
                    "urgency_level": "응급",
                    "urgency_level_num": 1,
                    "vtl_basis": f"Red flag {det_hit['id']}: {det_hit['label']}",
                    "red_flags": [det_hit["id"]],
                    "is_initial_visit": True,
                    "chief_complaint": rf_chief,
                    "symptom_keywords": [rf_chief],
                    "suspected_diseases": rf_suspected[:3],
                    "symptom_summary": f"즉시 내원이 필요한 응급 징후({det_hit['label']})가 확인된다.",
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
                rag_context = state.get("rag_context") or []
                freeform_turns = int(state.get("freeform_turns") or 1)
                user_messages = _session_user_messages(session)

                # 주제 이탈(파이썬 설명 등) → 리다이렉트. 상태 유지하고 완료/카운트 안 함.
                if await _is_offtopic(user_text, species):
                    await add_message(db, session, "assistant", _OFFTOPIC_REDIRECT, meta=state)
                    async for c in stream_msg(_OFFTOPIC_REDIRECT):
                        yield c
                    yield done_event
                    return

                if len(user_messages) < _FREEFORM_MIN_USER_TURNS and len(user_messages) < _FREEFORM_MAX_USER_TURNS:
                    followup, chips = await _freeform_reply(
                        symptom,
                        species,
                        rag_context,
                        conversation=user_messages,
                    )
                    new_state = {
                        "node_id": "FREEFORM",
                        "section": "GENERAL",
                        "answers": [],
                        "symptom": symptom,
                        "rag_context": rag_context,
                        "freeform_turns": freeform_turns + 1,
                    }
                    await add_message(db, session, "assistant", followup, meta=new_state)
                    async for c in stream_msg(followup):
                        yield c
                    yield f"data: {json.dumps({'type': 'quick_replies', 'options': chips, 'multi': False}, ensure_ascii=False)}\n\n"
                    yield done_event
                    return

                # freeform 단일 LLM 분석: 심각도 신호(B) + 키워드·의심질환·요약
                analysis = await _llm_freeform_analysis(symptom, user_messages, species, rag_context)
                # (A) 신호 → 트리와 동일 임계로 점수화
                freeform_urgency = te.compute_urgency(
                    te.freeform_severity_answers(analysis["signals"]), species, None, gender
                )
                logger.info(
                    "[Triage] freeform urgency session=%s score=%s → %s signals=%s",
                    session.id, freeform_urgency["total_score"], freeform_urgency["urgency"],
                    [k for k, v in analysis["signals"].items() if v],
                )
                collected_info = _freeform_collected_info(
                    symptom,
                    rag_context,
                    urgency=freeform_urgency,
                    analysis=analysis,
                )
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
            if not selected and user_text.strip():
                selected = _heuristic_classify_pills(node_id, user_text, species)
            if not selected and user_text.strip() and node_id != te.START_NODE:
                selected = _fallback_free_text_selection(node_id, user_text, species)
            if not selected:
                # START에서 응급 카테고리에 안 맞으면(피부·정기검진 등 비응급) 10개 보기를
                # 다시 쏟아내지 않고, 자연스럽게 알아듣고 부드러운 후속 질문 1개로 넘어간다.
                if node_id == te.START_NODE and user_text.strip():
                    # 주제 이탈(반려동물 건강과 무관) → 문진 시작 안 하고 리다이렉트, START 유지.
                    if await _is_offtopic(user_text, species):
                        await add_message(db, session, "assistant", _OFFTOPIC_REDIRECT, meta=state)
                        async for c in stream_msg(_OFFTOPIC_REDIRECT):
                            yield c
                        yield qr_event(te.START_NODE)
                        yield done_event
                        return
                    rag_context = await _search_triage_rag_context(db, user_text)
                    followup, chips = await _freeform_reply(user_text, species, rag_context)
                    new_state = {"node_id": "FREEFORM", "section": "GENERAL",
                                 "answers": [], "symptom": user_text,
                                 "rag_context": rag_context,
                                 "freeform_turns": 1}
                    await add_message(db, session, "assistant", followup, meta=new_state)
                    async for c in stream_msg(followup):
                        yield c
                    yield f"data: {json.dumps({'type': 'quick_replies', 'options': chips, 'multi': False}, ensure_ascii=False)}\n\n"
                    yield done_event
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
                selected_label = str(selected[0].get("label") or "").replace(" ", "")
                is_exact_start_pill = bool(selected_label and selected_label == user_text.replace(" ", ""))
                entry_node, entry_selected = (
                    (None, []) if is_exact_start_pill
                    else _entry_selections_from_text(section, species, user_text)
                )
                if entry_node and entry_selected:
                    answers += entry_selected
                    next_node = te.advance(entry_node, entry_selected)
                else:
                    next_node = te.advance(node_id, selected)
            else:
                answers = list(state["answers"]) + selected
                next_node = te.advance(node_id, selected)

            auto_selected, auto_next_node = _auto_answer_next_node(next_node, user_text, species)
            if auto_selected:
                answers += auto_selected
                next_node = auto_next_node

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
