"""Live triage turn runner.

This module owns the triage conversation decision:
- use JSON decision tree when the symptom is covered
- use RAG + LLM for off-tree/freeform symptoms
- fold image model observations into triage decisions
- decide when enough information was collected and return collected_info

`backend.app.api.chat` should stay as an API/SSE shell.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai.agents.base import call_openai
from ai.observability import get_langfuse_handler
from ai.triage import engine as te
from ai.triage.kb import detect_red_flag
from ai.triage.rag import TriageRagMatch, search_similar_triage_cases
from app.core.config import settings

logger = logging.getLogger(__name__)

INITIAL_MESSAGE = "어떤 증상 때문에 예약을 원하시나요?"
INITIAL_PILLS = ["기침/호흡", "구토/설사", "피부/눈/기타"]

_MISC_INITIAL_REPLY = "어느 부위에 어떤 변화가 보이나요? 보이는 모습이나 걱정되는 행동을 짧게 알려주세요."
_MISC_INITIAL_CHIPS = ["피부가 가렵거나 빨개요", "눈이 충혈되거나 눈물이 나요", "기타 증상이에요"]
_TRIAGE_RAG_TOP_K = 3
_TRIAGE_RAG_MIN_SIMILARITY = 0.60
_FREEFORM_MIN_USER_TURNS = 3
_FREEFORM_MAX_USER_TURNS = 5
_LOW_URGENCY_MAX_USER_TURNS = 5
_HIGH_URGENCY_MAX_USER_TURNS = 2
_MAX_QUICK_REPLIES = 3
_SECTION_TIMING_NODE = {
    "RESPIRATORY": "Q_RESP_TIMING",
    "SEIZURE": "Q_SEI_TIMING",
    "COLLAPSE": "Q_COL_TIMING",
    "BLEEDING": "Q_BLD_TIMING",
    "CARDIAC": "Q_CARD_TIMING",
    "UNABLE_TO_WALK": "Q_UTW_TIMING",
    "GI": "Q_GI_TIMING",
    "TRAUMA": "Q_TRA_TIMING",
    "UROGENITAL": "Q_URO_TIMING",
    "GENERAL": "Q_GEN_TIMING",
}

_SELECT_HINT_RE = re.compile(r"\s*[\(（][^)）]*선택[^)）]*[\)）]\s*$")
_FREEFORM_DEFAULT_REPLY = "걱정되시겠어요. 지금 보이는 변화가 번지거나 진물·출혈이 있는지도 알려주실 수 있을까요?"
_FREEFORM_DEFAULT_CHIPS = ["번지고 있어요", "진물이나 피가 나요", "그런 건 없어요"]
_OFFTOPIC_REDIRECT = (
    "저는 반려동물의 증상·건강 상담을 도와드리는 챗봇이에요. "
    "지금 어떤 증상이 있거나 걱정되는 부분을 알려주시면 도와드릴게요."
)
_FREEFORM_SIGNAL_KEYS = tuple(te.FREEFORM_SIGNAL_SCORES.keys())


@dataclass(slots=True)
class TriageTurnResult:
    reply: str
    quick_replies: list[str]
    multi: bool = False
    meta: dict | None = None
    collected_info: dict | None = None
    is_complete: bool = False
    guardian_safe: bool = False

    def __post_init__(self) -> None:
        self.quick_replies = _limit_quick_replies(self.quick_replies)


def _limit_quick_replies(options: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for option in options or []:
        text = content_text(option)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
        if len(result) >= _MAX_QUICK_REPLIES:
            break
    return result


def content_text(content: str | None) -> str:
    return " ".join((content or "").split())


def session_user_messages(messages: list[dict]) -> list[str]:
    return [
        content_text(m.get("content"))
        for m in (messages or [])
        if m.get("role") == "user" and content_text(m.get("content"))
    ]


def photo_triage_text(analysis: dict | None) -> str:
    if not analysis:
        return ""
    parts: list[str] = []
    visual = analysis.get("visual_observation")
    if isinstance(visual, dict):
        visible = [str(v).strip() for v in (visual.get("visible_changes") or []) if str(v).strip()]
        if visible:
            parts.append("사진 관찰: " + ", ".join(visible[:4]))
        location = str(visual.get("lesion_location") or "").strip()
        if location:
            parts.append(f"관찰 위치: {location}")
        focus = str(visual.get("question_focus") or "").strip()
        if focus:
            parts.append(f"확인 필요: {focus}")

    for key, label in (("skin", "피부 모델"), ("eye", "안구 모델")):
        item = analysis.get(key)
        if not isinstance(item, dict) or item.get("error"):
            continue
        top = str(item.get("top_1") or "").strip()
        if top:
            parts.append(f"{label}: {top}")
    return ("첨부 사진 AI 분석 참고자료. 확정 진단 아님. " + " / ".join(parts)) if parts else ""


def q_text(text: str) -> str:
    return _SELECT_HINT_RE.sub("", text or "").strip()


def load_walker_state(messages: list[dict]) -> dict:
    for message in reversed(messages or []):
        if message.get("role") == "assistant" and isinstance(message.get("meta"), dict):
            meta = message["meta"]
            return {
                "node_id": meta.get("node_id", te.START_NODE),
                "section": meta.get("section"),
                "answers": list(meta.get("answers") or []),
                "symptom": meta.get("symptom"),
                "rag_context": list(meta.get("rag_context") or []),
                "photo_context": meta.get("photo_context"),
                "freeform_turns": meta.get("freeform_turns"),
            }
    return {
        "node_id": te.START_NODE,
        "section": None,
        "answers": [],
        "symptom": None,
        "rag_context": [],
        "photo_context": None,
        "freeform_turns": None,
    }


def _match_user_selections(node_id: str, text: str) -> list[dict]:
    selected: list[dict] = []
    for segment in (text or "").split("\n"):
        pill = te.match_pill(node_id, segment)
        if pill and pill not in selected:
            selected.append(pill)
    return selected


def _initial_pill_selection(text: str) -> list[dict]:
    norm = (text or "").replace(" ", "")
    if not norm:
        return []
    start_pills = {p.get("value"): p for p in te.visible_pills(te.START_NODE)}
    if any(token in norm for token in ("기침", "호흡", "숨")) and "RESPIRATORY" in start_pills:
        return [start_pills["RESPIRATORY"]]
    if any(token in norm for token in ("구토", "설사", "토", "소화")) and "GI" in start_pills:
        return [start_pills["GI"]]
    return []


def _is_exact_misc_initial_choice(text: str) -> bool:
    norm = (text or "").replace(" ", "")
    return norm in {"피부/눈/기타", "피부눈기타", "기타증상이에요"}


def _is_misc_initial_text(text: str) -> bool:
    norm = (text or "").replace(" ", "")
    if not norm:
        return False
    if _is_exact_misc_initial_choice(text):
        return True
    return any(
        token in norm
        for token in (
            "피부", "눈", "안구", "귀", "털", "가려", "긁", "빨개", "빨갛", "붉",
            "발진", "두드러", "올라왔", "올라오", "부어", "붓", "탈모",
            "진물", "각질", "충혈", "눈물",
        )
    )


def _photo_indicates_misc(photo_analysis: dict | None, photo_context: str | None) -> bool:
    """사진 기반 피부/눈 신호는 START에서 외상 트리보다 freeform 문진을 우선한다."""
    if not photo_analysis and not photo_context:
        return False

    for key in ("skin", "eye"):
        item = photo_analysis.get(key) if isinstance(photo_analysis, dict) else None
        if not isinstance(item, dict) or item.get("error"):
            continue
        top_class = str(item.get("top_class") or "").lower()
        top_1 = str(item.get("top_1") or "").strip()
        if top_1 and top_class not in {"", "healthy", "normal"}:
            return True

    visual = photo_analysis.get("visual_observation") if isinstance(photo_analysis, dict) else None
    visual_text = ""
    if isinstance(visual, dict):
        visual_text = " ".join(
            str(value)
            for value in [
                *(visual.get("visible_changes") or []),
                visual.get("lesion_location") or "",
                visual.get("question_focus") or "",
            ]
        )

    combined = f"{photo_context or ''} {visual_text}".replace(" ", "")
    return any(
        token in combined
        for token in (
            "피부", "눈", "안구", "붉", "빨갛", "빨개", "발진", "두드러", "탈모",
            "털빠", "가려", "긁", "진물", "각질", "충혈", "눈물",
        )
    )


def _misc_detail_reply(
    raw_user_text: str,
    photo_analysis: dict | None,
    photo_context: str | None,
    has_photo: bool,
) -> tuple[str, list[str]]:
    text = f"{raw_user_text or ''} {photo_context or ''}".replace(" ", "")
    has_eye_model = False
    if isinstance(photo_analysis, dict):
        eye = photo_analysis.get("eye")
        has_eye_model = isinstance(eye, dict) and not eye.get("error")

    if has_eye_model or any(token in text for token in ("눈", "안구", "충혈", "눈물", "눈곱", "각막")):
        return (
            "눈 쪽 변화가 걱정되셨겠어요. 눈을 찡그리거나 비비고, 눈곱이나 분비물이 있나요?",
            ["눈을 비비거나 찡그려요", "눈곱이나 분비물이 있어요", "그런 건 없어요"],
        )

    if has_photo:
        reply = "사진상 피부가 붉게 올라온 변화가 보여요. 가려워하거나 핥고 긁는 행동이 있나요?"
    else:
        reply = "말씀하신 피부 변화가 걱정되셨겠어요. 가려워하거나 핥고 긁는 행동이 있나요?"
    return reply, ["계속 긁거나 핥아요", "진물이나 피가 나요", "그런 건 없어요"]


def _skin_freeform_followup(
    symptom: str,
    user_messages: list[str],
    photo_context: str | None,
) -> tuple[str, list[str]] | None:
    """피부 freeform은 이미 답한 슬롯을 다시 묻지 않도록 결정론으로 다음 질문을 고른다."""
    combined = " ".join([symptom or "", *(user_messages or []), photo_context or ""]).replace(" ", "")
    answered = " ".join([symptom or "", *(user_messages or [])]).replace(" ", "")
    is_skin = any(
        token in combined
        for token in (
            "피부", "붉", "빨갛", "빨개", "발진", "두드러", "탈모", "털빠",
            "가려", "긁", "핥", "진물", "각질",
        )
    )
    if not is_skin:
        return None

    has_itch = any(token in answered for token in ("가려", "긁", "핥", "비비", "간지"))
    has_discharge = any(token in answered for token in ("진물", "피", "출혈", "고름", "딱지", "젖어"))
    has_spread = any(token in answered for token in ("번지", "퍼지", "커졌", "커지", "넓어", "크기"))
    has_pain = any(token in answered for token in ("아파", "통증", "만지면싫", "예민", "피하"))

    if has_itch and not has_discharge:
        return (
            "긁으려고 하는군요. 그 부위에 진물이나 피, 딱지처럼 보이는 것도 있나요?",
            ["진물이나 피가 나요", "딱지가 있어요", "그런 건 없어요"],
        )
    if (has_itch or has_discharge) and not has_spread:
        return (
            "확인 고마워요. 붉은 부위가 어제보다 넓어지거나 다른 곳으로 번지고 있나요?",
            ["점점 번지고 있어요", "크기는 비슷해요", "잘 모르겠어요"],
        )
    if (has_itch or has_discharge or has_spread) and not has_pain:
        return (
            "마지막으로, 그 부위를 만지면 아파하거나 예민하게 반응하나요?",
            ["만지면 아파해요", "예민하긴 해요", "통증은 없어 보여요"],
        )
    return None


def _timing_answer_from_text(node_id: str | None, text: str) -> dict | None:
    if not node_id:
        return None
    node = te.get_node(node_id) or {}
    if not node.get("is_timing"):
        return None
    compact = (text or "").replace(" ", "")
    if not compact:
        return None

    value: str | None = None
    if any(token in compact for token in ("수분", "1시간", "방금", "지금막", "갑자기지금")):
        value = "abrupt"
    elif any(token in compact for token in ("오늘", "오늘부터", "하루안", "몇시간")):
        value = "rapid"
    elif any(token in compact for token in ("어제", "어젯", "2일", "3일", "이틀", "삼일", "며칠")):
        value = "acute"
    elif any(token in compact for token in ("1주", "일주", "오래", "계속그랬", "만성")):
        value = "recent"
    if not value:
        return None

    by_value = {p.get("value"): p for p in te.visible_pills(node_id)}
    pill = by_value.get(value)
    if not pill and value == "rapid":
        pill = by_value.get("abrupt") or by_value.get("acute")
    if not pill and value == "acute":
        pill = by_value.get("recent")
    return {**pill, "is_timing": True} if pill else None


def _contextual_red_flag(text: str, node_id: str | None, section: str | None) -> dict | None:
    """트리 질문 문맥상 red flag로 해석해야 하는 자연어를 보강 감지한다."""
    compact = (text or "").replace(" ", "")
    if not compact:
        return None

    def hit(fid: str, label: str, chief: str, suspected: list[str]) -> dict:
        return {
            "id": fid,
            "label": label,
            "source": "contextual",
            "chief": chief,
            "suspected": suspected,
        }

    seizure_context = section == "SEIZURE" or node_id in {te.START_NODE, "Q_SEI_01"}
    has_seizure = any(token in compact for token in ("발작", "경련", "바들바들", "부들부들"))
    active_now = any(
        token in compact
        for token in (
            "방금", "지금", "시작됐", "시작했", "시작", "하고있", "하는중",
            "일어나고", "안멈", "멈추지", "계속",
        )
    )
    past_only = any(token in compact for token in ("멈췄", "끝났", "지금은괜찮", "아까했", "오늘있었"))
    if seizure_context and has_seizure and active_now and not past_only:
        return hit("RF-01", "지금 발작 중이에요", "발작", ["특발성 발작", "중독", "대사성 질환"])

    if any(token in compact for token in ("숨못쉬", "숨을못쉬", "숨이안쉬", "입벌리고헐떡", "개구호흡", "호흡곤란")):
        return hit("RF-02", "숨을 거의 못 쉬어요 / 입을 벌리고 헐떡여요", "호흡곤란", ["폐부종", "흉수/기흉", "상기도 폐쇄"])

    if any(token in compact for token in ("의식없", "의식이없", "반응없", "반응이없", "못깨워", "정신잃", "정신을잃")):
        return hit("RF-03", "완전히 의식이 없어요 (반응 없음)", "의식소실", ["쇼크", "중독", "두부 외상"])

    if any(token in compact for token in ("혀가파래", "혀가보라", "잇몸이파래", "잇몸이보라", "청색증")):
        return hit("RF-04", "잇몸/혀가 파래요 (청색증)", "청색증", ["저산소증", "심부전", "폐질환"])

    if any(token in compact for token in ("배가갑자기부", "배가갑자기커", "배가빵빵", "복부팽만")) and any(
        token in compact for token in ("방금", "갑자기", "오늘", "구토", "토하", "토해")
    ):
        return hit("RF-05", "배가 갑자기 크게 부풀었어요 (30분~12시간)", "급성 복부팽만", ["위확장염전(GDV)", "복강내 출혈"])

    if any(token in compact for token in ("내장이나왔", "장기가나왔", "내장이튀어나", "장이보여")):
        return hit("RF-07", "내장이 밖으로 나왔어요", "장기 노출", ["복벽 열창", "장 탈출"])

    if any(token in compact for token in ("눈이튀어나", "눈알이빠", "안구돌출")):
        return hit("RF-08", "눈이 튀어나왔어요", "안구 돌출", ["안구 탈출", "안와 외상"])

    if any(token in compact for token in ("피가안멈", "피가멈추지", "피가콸콸", "피가쏟아", "피를많이흘", "대량출혈", "피를토")):
        return hit("RF-09", "피가 멈추지 않고 쏟아져요", "대량 출혈", ["응고장애", "대혈관 손상", "저혈량 쇼크"])

    if any(token in compact for token in ("잇몸이창백", "잇몸이하얘", "창백하고쓰러", "쇼크")):
        return hit("RF-11", "잇몸이 창백하고 쓰러졌어요", "허탈/창백", ["쇼크", "내출혈", "패혈증"])

    if any(token in compact for token in ("소변전혀못", "소변을전혀못", "오줌전혀못", "오줌을전혀못", "소변이안나", "오줌이안나")) or (
        any(token in compact for token in ("소변", "오줌")) and any(token in compact for token in ("12시간", "하루종일", "못봐", "못쌌", "못싸"))
    ):
        return hit("RF-12", "소변을 12시간 이상 전혀 못 봐요", "배뇨 불가", ["요도폐색", "급성 신손상"])

    if any(token in compact for token in ("독사", "뱀에물", "독거미", "거미에물", "지네에물")):
        return hit("RF-14", "독사/독거미에 물렸어요", "독성 교상", ["독사/독거미 교상"])

    if any(token in compact for token in ("몸이차갑", "체온이낮", "저체온")) and any(
        token in compact for token in ("축늘", "기운없", "반응없", "쓰러")
    ):
        return hit("RF-15", "체온이 너무 낮아요 (몸이 차갑고 축 늘어짐)", "저체온", ["쇼크", "저체온증"])
    return None


def _has_timing_answer(answers: list[dict]) -> bool:
    return any(a.get("is_timing") or a.get("urgency_modifier") is not None for a in answers)


def _add_timing_if_mentioned(answers: list[dict], section: str | None, text: str) -> list[dict]:
    if _has_timing_answer(answers):
        return answers
    timing = _timing_answer_from_text(_SECTION_TIMING_NODE.get(section or ""), text)
    return [*answers, timing] if timing else answers


def _should_finish_triage(
    answers: list[dict],
    section: str | None,
    species: str | None,
    gender: str | None,
    user_turns: int,
    next_node: str | None,
) -> bool:
    if not answers or section is None:
        return False
    if next_node is None:
        return True
    if _has_timing_answer(answers) and (te.get_node(next_node) or {}).get("is_timing"):
        return True

    urgency = te.compute_urgency(answers, species, section, gender)
    urgency_num = urgency.get("urgency_level_num", 4)
    if urgency_num <= 2 and (_has_timing_answer(answers) or user_turns >= _HIGH_URGENCY_MAX_USER_TURNS):
        return True
    clinical_answers = [a for a in answers if not (a.get("is_timing") or a.get("urgency_modifier") is not None)]
    if urgency_num >= 3 and _has_timing_answer(answers) and clinical_answers and user_turns >= 2:
        return True
    return user_turns >= _LOW_URGENCY_MAX_USER_TURNS


async def _llm_classify_pills(node_id: str, user_text: str, species: str | None) -> list[dict]:
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
        values = (json.loads(resp.content if isinstance(resp.content, str) else "{}") or {}).get("values") or []
    except Exception as exc:
        logger.warning("[Triage] free-text classification failed node=%s: %s", node_id, exc)
        return []
    by_value = {p["value"]: p for p in pills}
    matched = [by_value[v] for v in values if v in by_value]
    return matched if multi else matched[:1]


def _heuristic_classify_pills(node_id: str, user_text: str, species: str | None) -> list[dict]:
    text = (user_text or "").replace(" ", "")
    if not text:
        return []
    pills = te.visible_pills(node_id, species)
    by_value = {p.get("value"): p for p in pills}
    values: list[str] = []

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
        for section, keywords in section_keywords:
            if section in by_value and any(keyword in text for keyword in keywords):
                return [by_value[section]]
        if "GENERAL" in by_value and any(
            keyword in text for keyword in ("기운없", "기운이없", "기력", "축처", "안먹", "밥안", "식욕", "무기력", "못먹")
        ):
            return [by_value["GENERAL"]]
        return []

    timing = _timing_answer_from_text(node_id, user_text)
    if timing:
        return [timing]

    if node_id == "Q_SEI_01":
        compact = (user_text or "").replace(" ", "")
        if any(token in compact for token in ("방금", "지금", "시작됐", "시작했", "하고있", "안멈", "계속")):
            current = next((p for p in pills if p.get("red_flag")), None)
            if current:
                return [current]

    def choose(value: str) -> None:
        if value in by_value and value not in values:
            values.append(value)

    if node_id == "Q_RESP_SOUND":
        if any(token in text for token in ("계속", "자주", "많이", "심해", "하루종일", "잦")):
            choose("persistent")
        elif any(token in text for token in ("가끔", "조금", "몇번", "한두번")):
            choose("occasional")
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
    return matched if te.is_multi(node_id) else matched[:1]


def _auto_answer_next_node(next_node: str | None, user_text: str, species: str | None) -> tuple[list[dict], str | None]:
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
    text = content_text(user_text)
    if not text or node_id == te.START_NODE:
        return []
    node = te.get_node(node_id) or {}
    pills = te.visible_pills(node_id, species)
    if not node or not pills:
        return []
    node_next = node.get("next")
    base = {"label": text[:120], "value": "free_text", "urgency_score": 0, "keywords": [], "free_text": True}
    if node.get("type") == "multi":
        return [{**base, "next": node_next}] if node_next else [base]
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
    return [{**base, "next": node_next}] if node_next else [base]


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
    return [_rag_match_to_meta(m) for m in matches if m.similarity >= _TRIAGE_RAG_MIN_SIMILARITY]


async def _search_triage_rag_context(db: AsyncSession, query: str) -> list[dict]:
    if not (query or "").strip():
        return []
    try:
        matches = await search_similar_triage_cases(db, query, top_k=_TRIAGE_RAG_TOP_K)
        context = _usable_rag_context(matches)
        if matches:
            logger.info("[TriageRAG] query=%r top_similarity=%.4f usable=%d/%d", query[:80], matches[0].similarity, len(context), len(matches))
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
            f"진료과 {item.get('department') or '미상'} / 질환 {item.get('disease') or '미상'}"
        )
        lines.append(f"- 유사 질문: {str(item.get('input_text') or '')[:240]}")
        lines.append(f"- 사례 답변 요지: {str(item.get('output_text') or '')[:300]}")
    lines.append("위 자료는 확정 진단이 아니라 다음 질문을 더 잘 고르기 위한 참고자료입니다. 보호자에게 병명을 단정하지 마세요.")
    return "\n".join(lines)


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = content_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


_FREEFORM_SLOT_RULES = (
    {
        "name": "onset",
        "answered": ("오늘", "어제", "어젯", "부터", "이틀", "삼일", "며칠", "일주", "방금", "아까"),
        "question": ("언제부터", "시작", "얼마나됐", "며칠", "시점"),
        "reply": "증상이 언제부터 보였는지 알려주실 수 있을까요?",
        "chips": ["오늘부터요", "어제부터요", "며칠 됐어요"],
    },
    {
        "name": "itch",
        "answered": ("가려", "긁", "핥", "비비", "간지"),
        "question": ("가려", "긁", "핥", "비비", "간지"),
        "reply": "가려워하거나 핥고 긁는 행동이 있나요?",
        "chips": ["계속 긁거나 핥아요", "가끔 그래요", "그런 건 없어요"],
    },
    {
        "name": "frequency",
        "answered": ("한번", "두번", "세번", "여러번", "계속", "자주", "반복", "가끔", "많이"),
        "question": ("몇번", "얼마나자주", "빈도", "반복", "계속"),
        "reply": "그 증상이 얼마나 자주 보이나요?",
        "chips": ["계속 보여요", "가끔 보여요", "한두 번 정도예요"],
    },
    {
        "name": "breathing_effort",
        "answered": ("숨", "호흡", "헐떡", "쌕쌕", "입벌", "배로숨", "숨가"),
        "question": ("숨", "호흡", "헐떡", "쌕쌕", "입벌", "배로숨"),
        "reply": "숨쉬는 모습은 평소보다 힘들어 보이나요?",
        "chips": ["숨쉬기 힘들어 보여요", "소리가 나요", "그 정도는 아니에요"],
    },
    {
        "name": "pain",
        "answered": ("아파", "통증", "만지면싫", "예민", "낑낑", "절뚝", "불편"),
        "question": ("아파", "통증", "만지면", "예민", "불편"),
        "reply": "아파하거나 만지면 싫어하는 반응이 있나요?",
        "chips": ["아파해요", "예민하게 반응해요", "통증은 없어 보여요"],
    },
    {
        "name": "bleeding_discharge",
        "answered": ("피나", "피가", "피흘", "출혈", "진물", "고름", "분비물", "딱지", "눈곱", "토혈", "혈변", "혈뇨"),
        "question": ("피나", "피가", "출혈", "진물", "고름", "분비물", "딱지", "눈곱", "혈"),
        "reply": "피나 진물, 분비물처럼 같이 보이는 변화가 있나요?",
        "chips": ["피나 진물이 있어요", "분비물이 있어요", "그런 건 없어요"],
    },
    {
        "name": "spread_change",
        "answered": ("번지", "퍼지", "커졌", "커지", "넓어", "줄어", "심해", "나아"),
        "question": ("번지", "퍼지", "커지", "넓어", "심해", "변화"),
        "reply": "처음 봤을 때보다 범위나 정도가 달라졌나요?",
        "chips": ["점점 심해져요", "비슷해요", "조금 나아졌어요"],
    },
    {
        "name": "appetite_activity",
        "answered": ("밥", "식욕", "먹", "기운", "활력", "축", "무기력", "잠"),
        "question": ("밥", "식욕", "먹", "기운", "활력", "축", "무기력"),
        "reply": "밥 먹는 양이나 기운은 평소와 비슷한가요?",
        "chips": ["밥을 잘 안 먹어요", "기운이 없어요", "평소와 비슷해요"],
    },
    {
        "name": "urine_stool",
        "answered": ("소변", "오줌", "대변", "변", "설사", "혈뇨", "혈변", "못싸", "못봐"),
        "question": ("소변", "오줌", "대변", "변", "설사", "배변", "배뇨"),
        "reply": "소변이나 대변은 평소와 다른 점이 있나요?",
        "chips": ["소변이 달라졌어요", "대변이 달라졌어요", "평소와 비슷해요"],
    },
)

_FREEFORM_DEFAULT_SLOT_ORDER = (
    "onset",
    "frequency",
    "pain",
    "bleeding_discharge",
    "appetite_activity",
    "urine_stool",
)
_FREEFORM_TOPIC_SLOT_ORDER = {
    "skin": ("onset", "itch", "bleeding_discharge", "spread_change", "pain", "appetite_activity"),
    "eye": ("onset", "pain", "bleeding_discharge", "spread_change", "appetite_activity"),
    "gi": ("onset", "frequency", "bleeding_discharge", "appetite_activity", "pain"),
    "respiratory": ("onset", "breathing_effort", "frequency", "appetite_activity"),
    "urogenital": ("onset", "urine_stool", "pain", "appetite_activity"),
    "mobility": ("onset", "pain", "frequency", "appetite_activity"),
}
_FREEFORM_SLOT_BY_NAME = {str(rule["name"]): rule for rule in _FREEFORM_SLOT_RULES}


def _freeform_slot_names(text: str, key: str) -> set[str]:
    compact = (text or "").replace(" ", "")
    if not compact:
        return set()
    return {
        str(rule["name"])
        for rule in _FREEFORM_SLOT_RULES
        if any(token in compact for token in rule[key])
    }


def _fallback_unanswered_slot_question(answered_slots: set[str]) -> tuple[str, list[str]] | None:
    for rule in _FREEFORM_SLOT_RULES:
        if str(rule["name"]) not in answered_slots:
            return str(rule["reply"]), _limit_quick_replies(list(rule["chips"]))
    return None


def _freeform_topic(text: str) -> str:
    compact = (text or "").replace(" ", "")
    if any(token in compact for token in ("피부", "붉", "빨갛", "빨개", "발진", "가려", "긁", "핥", "탈모", "털빠")):
        return "skin"
    if any(token in compact for token in ("눈", "안구", "충혈", "눈물", "눈곱", "각막")):
        return "eye"
    if any(token in compact for token in ("구토", "토하", "토해", "설사", "혈변", "대변", "배가", "복부", "먹었")):
        return "gi"
    if any(token in compact for token in ("기침", "숨", "호흡", "헐떡", "쌕쌕", "재채기")):
        return "respiratory"
    if any(token in compact for token in ("소변", "오줌", "혈뇨", "방광", "배뇨")):
        return "urogenital"
    if any(token in compact for token in ("절뚝", "다리", "못걷", "관절", "발", "걷")):
        return "mobility"
    return "general"


def _planned_freeform_followup(
    symptom: str,
    user_messages: list[str],
    photo_context: str | None,
) -> tuple[str, list[str]] | None:
    """같은 증상군은 같은 슬롯 순서로 질문해 흐름을 안정화한다."""
    combined = " ".join([symptom or "", *(user_messages or []), photo_context or ""])
    answered_text = " ".join([symptom or "", *(user_messages or [])])
    answered_slots = _freeform_slot_names(answered_text, "answered")
    topic = _freeform_topic(combined)
    order = _FREEFORM_TOPIC_SLOT_ORDER.get(topic, _FREEFORM_DEFAULT_SLOT_ORDER)
    for slot_name in order:
        if slot_name in answered_slots:
            continue
        rule = _FREEFORM_SLOT_BY_NAME.get(slot_name)
        if rule:
            return str(rule["reply"]), _limit_quick_replies(list(rule["chips"]))
    return None


def _avoid_repeated_freeform_question(
    reply: str,
    chips: list[str],
    symptom: str,
    user_messages: list[str],
) -> tuple[str, list[str]]:
    """LLM이 이미 답한 슬롯을 다시 물으면 다음 미확인 슬롯 질문으로 교체한다."""
    answered_text = " ".join([symptom or "", *(user_messages or [])])
    answered_slots = _freeform_slot_names(answered_text, "answered")
    question_slots = _freeform_slot_names(" ".join([reply or "", *(chips or [])]), "question")
    repeated = answered_slots & question_slots
    if not repeated:
        return reply, chips

    fallback = _fallback_unanswered_slot_question(answered_slots)
    if fallback:
        return fallback
    return "추가로 평소와 다르게 보이는 점이 있나요?", ["있어요", "없어요", "잘 모르겠어요"]


def _entry_selections_from_text(section: str | None, species: str | None, text: str) -> tuple[str | None, list[dict]]:
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


async def _freeform_reply(
    symptom: str,
    species: str | None,
    rag_context: list[dict] | None = None,
    conversation: list[str] | None = None,
) -> tuple[str, list[str]]:
    animal = "고양이" if species == "cat" else "강아지"
    rag_prompt = _format_rag_context_for_prompt(rag_context or [])
    asked = _dedupe_texts(conversation or [])
    asked_block = ("이미 나눈 대화: " + " / ".join(asked[-6:]) + "\n") if asked else ""
    system = (
        f"너는 동물병원 AI 상담 도우미야. 보호자가 {animal} 증상으로 '{symptom}'라고 말했어.\n"
        f"{asked_block}"
        "당장 생명을 위협하는 응급은 아닌 일반 증상이야. 다음 규칙으로 JSON을 만들어:\n"
        "- reply: 공감 한 문장 + 증상을 더 파악하기 위한 자연스러운 질문 1개. 보호자가 관찰로 답할 수 있는 쉬운 질문만.\n"
        "- quick_replies: 그 질문에 보호자가 바로 고를 수 있는 짧은 보기 3개.\n"
        "- 유사 상담 사례가 있으면 그 방향의 핵심 확인을 우선하되 병명은 단정하지 마.\n"
        "- 보호자가 이미 말한 정보(부위, 시점, 증상 모양)나 사진에서 보이는 변화는 다시 묻지 마.\n"
        "- 시점이 있으면 언제부터인지 묻지 말고, 가려움·핥음/긁음·통증·번짐·진물/출혈 같은 다음 미확인 정보 중 하나만 물어.\n"
        "- 사진/문장에 피부가 빨갛다는 정보가 있으면 어느 부위/어떤 변화를 다시 묻지 마.\n"
        "- 이미 나눈 대화와 같은 질문 반복 금지. 병명 단정·응급/생명위협 표현 금지. 따뜻하고 짧게.\n"
        + (f"\n{rag_prompt}\n" if rag_prompt else "")
        + 'JSON만 출력: {"reply":"...","quick_replies":["...","...","..."]}'
    )
    try:
        result = await call_openai([{"role": "user", "content": symptom}], system, max_tokens=300, agent="triage_freeform")
        if isinstance(result, dict):
            text = str(result.get("reply") or "").strip() or _FREEFORM_DEFAULT_REPLY
            chips = [str(c).strip() for c in (result.get("quick_replies") or []) if str(c).strip()][:3]
            return text, (chips or _FREEFORM_DEFAULT_CHIPS)
    except Exception as exc:
        logger.warning("[Triage] freeform reply failed: %s", exc)
    return _FREEFORM_DEFAULT_REPLY, _FREEFORM_DEFAULT_CHIPS


async def _is_offtopic(text: str, species: str | None) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    system = (
        "너는 동물병원 '증상 상담 챗봇'의 입력 주제 필터야. 사용자 메시지가 "
        "반려동물의 건강·증상·상태·행동·복약·진료/예약과 조금이라도 관련 있으면 related, "
        "그 외면 unrelated 로 분류해. 증상이 모호하거나 짧아도 동물 건강과 관련될 여지가 있으면 related 로 둬.\n"
        'JSON만 출력: {"topic": "related"} 또는 {"topic": "unrelated"}'
    )
    try:
        result = await call_openai([{"role": "user", "content": text[:500]}], system, max_tokens=20, agent="triage_topic_guard")
        return isinstance(result, dict) and str(result.get("topic") or "").strip().lower() == "unrelated"
    except Exception as exc:
        logger.warning("[Triage] offtopic check failed: %s", exc)
    return False


def _format_rag_for_freeform(rag_context: list[dict] | None) -> str:
    if not rag_context:
        return ""
    lines = ["참고 유사 상담사례(진단 단정 금지, 표현 참고용):"]
    for item in rag_context[:3]:
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
    photo_context: str | None = None,
) -> dict:
    convo = " / ".join(_dedupe_texts([symptom, *(user_messages or []), photo_context or ""]))[:1200]
    animal = "고양이" if species == "cat" else "강아지"
    rag_block = _format_rag_for_freeform(rag_context)
    system = (
        f"너는 동물병원 트리아지 보조야. 보호자가 {animal} 증상을 다음처럼 설명했어:\n"
        f'"{convo}"\n\n'
        + (rag_block + "\n\n" if rag_block else "")
        + "대화를 바탕으로 아래 JSON을 채워. 대화에 없는 증상 추가·과장·진단 단정 금지.\n"
        "- signals: 각 항목이 대화에 명확히 드러나면 true, 아니면 false\n"
        "    systemic_signs, rapid_worsening, severe_pain, active_bleeding, prolonged\n"
        "- chief_complaint: 주요 증상 한 줄\n"
        "- symptom_keywords: 핵심 증상 키워드 2~5개\n"
        "- suspected_diseases: 가능성 있는 질환 0~3개(불확실하면 빈 배열, 단정 금지)\n"
        "- symptom_summary: SOAP의 S에 해당하는 한 줄 요약. 평서형 종결.\n\n"
        'JSON만 출력: {"signals":{"systemic_signs":false,"rapid_worsening":false,'
        '"severe_pain":false,"active_bleeding":false,"prolonged":false},'
        '"chief_complaint":"","symptom_keywords":[],"suspected_diseases":[],"symptom_summary":""}'
    )
    try:
        result = await call_openai([{"role": "user", "content": convo}], system, max_tokens=400, agent="triage_freeform_analysis")
        if isinstance(result, dict):
            sig = result.get("signals") or {}
            return {
                "signals": {k: bool(sig.get(k)) for k in _FREEFORM_SIGNAL_KEYS},
                "chief_complaint": str(result.get("chief_complaint") or "").strip(),
                "symptom_keywords": [str(v).strip() for v in (result.get("symptom_keywords") or []) if str(v).strip()][:5],
                "suspected_diseases": [str(v).strip() for v in (result.get("suspected_diseases") or []) if str(v).strip()][:3],
                "symptom_summary": str(result.get("symptom_summary") or "").strip(),
            }
    except Exception as exc:
        logger.warning("[Triage] freeform analysis failed: %s", exc)
    return _empty_freeform_analysis()


def _freeform_collected_info(
    symptom: str,
    rag_context: list[dict] | None = None,
    urgency: dict | None = None,
    analysis: dict | None = None,
) -> dict:
    u = urgency or {"urgency_level": "일반", "urgency_level_num": 4, "urgency": "GREEN", "total_score": 0}
    analysis = analysis or _empty_freeform_analysis()
    rag_context = rag_context or []
    rag_basis = ""
    if rag_context:
        top = rag_context[0]
        rag_basis = f" / rag top={top.get('department')}/{top.get('disease')} sim={float(top.get('similarity') or 0):.2f}"

    keywords = analysis.get("symptom_keywords") or []
    diseases = list(analysis.get("suspected_diseases") or [])
    for item in rag_context:
        disease = (item.get("disease") or "").strip()
        if disease and disease != "기타" and disease not in diseases:
            diseases.append(disease)
    summary = analysis.get("symptom_summary") or content_text(symptom)[:300]
    chief = analysis.get("chief_complaint") or (keywords[0] if keywords else content_text(symptom)[:40])
    num = u["urgency_level_num"]
    need_followup, followup_reason = te.compute_need_followup(
        urgency_level_num=num, dynamic_signals=analysis.get("signals"),
    )
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
        "need_followup": need_followup,
        "followup_reason": followup_reason,
    }


def quick_replies_for_node(node_id: str, species: str | None) -> tuple[list[str], bool]:
    if node_id == te.START_NODE:
        return INITIAL_PILLS, False
    return _limit_quick_replies(te.pill_labels(node_id, species)), te.is_multi(node_id)


async def run_triage_turn(
    *,
    db: AsyncSession,
    messages: list[dict],
    raw_user_text: str,
    image_url: str | None,
    photo_analysis: dict | None,
    species: str | None,
    gender: str | None,
) -> TriageTurnResult:
    species = species or "dog"
    raw_user_text = raw_user_text or ""
    photo_context = photo_triage_text(photo_analysis)
    user_text = "\n".join(part for part in (raw_user_text, photo_context) if part).strip()
    display_text = raw_user_text or ("첨부 사진을 확인해 주세요." if image_url else "")
    state = load_walker_state(messages)
    node_id = state["node_id"]
    user_turns = len(session_user_messages(messages))

    clicked_pill = bool(node_id != te.START_NODE and _match_user_selections(node_id, raw_user_text))
    red_flag = None if clicked_pill else (
        _contextual_red_flag(user_text, node_id, state.get("section"))
        or detect_red_flag(user_text)
    )
    if red_flag:
        chief = red_flag.get("chief") or red_flag["label"]
        collected_info = {
            "is_triage_complete": True,
            "urgency_level": "응급",
            "urgency_level_num": 1,
            "vtl_basis": f"Red flag {red_flag['id']}: {red_flag['label']}",
            "red_flags": [red_flag["id"]],
            "is_initial_visit": True,
            "chief_complaint": chief,
            "symptom_keywords": [chief],
            "suspected_diseases": (red_flag.get("suspected") or [])[:3],
            "symptom_summary": f"즉시 내원이 필요한 응급 징후({red_flag['label']})가 확인된다.",
            "recommended_action": "즉시 내원",
            "need_followup": True,
            "followup_reason": f"응급 red flag: {red_flag['label']}",
        }
        return TriageTurnResult(
            reply="말씀해 주셔서 감사해요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요.",
            quick_replies=[],
            collected_info=collected_info,
            is_complete=True,
            guardian_safe=True,
        )

    if node_id == "FREEFORM":
        symptom = state.get("symptom") or user_text
        rag_context = state.get("rag_context") or []
        state_photo_context = state.get("photo_context") or photo_context
        user_messages = session_user_messages(messages)
        if await _is_offtopic(user_text, species):
            return TriageTurnResult(reply=_OFFTOPIC_REDIRECT, quick_replies=[], meta=state)

        if len(user_messages) < _FREEFORM_MIN_USER_TURNS and len(user_messages) < _FREEFORM_MAX_USER_TURNS:
            skin_followup = _skin_freeform_followup(symptom, user_messages, state_photo_context)
            if skin_followup:
                followup, chips = skin_followup
            else:
                planned_followup = _planned_freeform_followup(symptom, user_messages, state_photo_context)
                if planned_followup:
                    followup, chips = planned_followup
                else:
                    followup, chips = await _freeform_reply(
                        symptom,
                        species,
                        rag_context,
                        conversation=[*user_messages, state_photo_context or ""],
                    )
            followup, chips = _avoid_repeated_freeform_question(followup, chips, symptom, user_messages)
            return TriageTurnResult(
                reply=followup,
                quick_replies=chips,
                meta={
                    "node_id": "FREEFORM",
                    "section": "GENERAL",
                    "answers": [],
                    "symptom": symptom,
                    "rag_context": rag_context,
                    "photo_context": state_photo_context,
                    "freeform_turns": int(state.get("freeform_turns") or 1) + 1,
                },
            )

        analysis = await _llm_freeform_analysis(symptom, user_messages, species, rag_context, state_photo_context)
        urgency = te.compute_urgency(te.freeform_severity_answers(analysis["signals"]), species, None, gender)
        return TriageTurnResult(
            reply="증상 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요.",
            quick_replies=[],
            collected_info=_freeform_collected_info(symptom, rag_context, urgency=urgency, analysis=analysis),
            is_complete=True,
            guardian_safe=True,
        )

    if node_id == te.START_NODE and (
        _is_misc_initial_text(raw_user_text)
        or _photo_indicates_misc(photo_analysis, photo_context)
    ):
        symptom_text = display_text or raw_user_text or "피부/눈/기타"
        rag_context = await _search_triage_rag_context(db, user_text) if user_text.strip() else []
        has_detail_or_photo = bool(photo_context or image_url or (raw_user_text and not _is_exact_misc_initial_choice(raw_user_text)))
        if has_detail_or_photo:
            reply, chips = _misc_detail_reply(raw_user_text, photo_analysis, photo_context, has_photo=bool(image_url))
        else:
            reply, chips = _MISC_INITIAL_REPLY, _MISC_INITIAL_CHIPS
        return TriageTurnResult(
            reply=reply,
            quick_replies=chips,
            meta={
                "node_id": "FREEFORM",
                "section": "GENERAL",
                "answers": [],
                "symptom": symptom_text,
                "rag_context": rag_context,
                "photo_context": photo_context,
                "freeform_turns": 1,
            },
        )

    selected = _initial_pill_selection(raw_user_text) if node_id == te.START_NODE else []
    if not selected:
        selected = _match_user_selections(node_id, raw_user_text)
    if not selected and user_text.strip():
        selected = await _llm_classify_pills(node_id, user_text, species)
    if not selected and user_text.strip():
        selected = _heuristic_classify_pills(node_id, user_text, species)
    if not selected and user_text.strip() and node_id != te.START_NODE:
        selected = _fallback_free_text_selection(node_id, user_text, species)

    if not selected:
        if node_id == te.START_NODE and user_text.strip():
            if await _is_offtopic(user_text, species):
                options, multi = quick_replies_for_node(te.START_NODE, species)
                return TriageTurnResult(reply=_OFFTOPIC_REDIRECT, quick_replies=options, multi=multi, meta=state)
            rag_context = await _search_triage_rag_context(db, user_text)
            symptom_text = display_text or user_text
            planned_followup = _planned_freeform_followup(symptom_text, [], photo_context)
            if planned_followup:
                followup, chips = planned_followup
            else:
                followup, chips = await _freeform_reply(
                    symptom_text,
                    species,
                    rag_context,
                    conversation=([photo_context] if photo_context else None),
                )
            return TriageTurnResult(
                reply=followup,
                quick_replies=chips,
                meta={
                    "node_id": "FREEFORM",
                    "section": "GENERAL",
                    "answers": [],
                    "symptom": symptom_text,
                    "rag_context": rag_context,
                    "photo_context": photo_context,
                    "freeform_turns": 1,
                },
            )
        options, multi = quick_replies_for_node(node_id, species)
        return TriageTurnResult(reply="조금 더 구체적으로 말씀해 주시거나, 아래 보기 중에서 골라 주세요.", quick_replies=options, multi=multi, meta=state)

    section = state.get("section")
    if node_id == te.START_NODE:
        section = selected[0].get("next_section") or selected[0].get("value")
        answers = list(state["answers"])
        selected_label = str(selected[0].get("label") or "").replace(" ", "")
        exact_start_pill = bool(selected_label and selected_label == raw_user_text.replace(" ", ""))
        entry_node, entry_selected = (None, []) if exact_start_pill else _entry_selections_from_text(section, species, user_text)
        if entry_node and entry_selected:
            answers += entry_selected
            next_node = te.advance(entry_node, entry_selected)
        else:
            next_node = te.advance(node_id, selected)
        answers = _add_timing_if_mentioned(answers, section, user_text)
    else:
        answers = list(state["answers"]) + selected
        next_node = te.advance(node_id, selected)
        answers = _add_timing_if_mentioned(answers, section, user_text)

    auto_selected, auto_next_node = _auto_answer_next_node(next_node, user_text, species)
    if auto_selected:
        answers += auto_selected
        next_node = auto_next_node

    if _should_finish_triage(answers, section, species, gender, user_turns, next_node):
        return TriageTurnResult(
            reply="증상을 잘 알려주셨어요. 바로 진료 예약을 도와드릴게요. 잠시만 기다려 주세요.",
            quick_replies=[],
            collected_info=te.to_collected_info(answers, species, section, gender),
            is_complete=True,
            guardian_safe=True,
        )

    q = te.get_node(next_node)
    options, multi = quick_replies_for_node(next_node, species)
    return TriageTurnResult(
        reply=f"확인 도와드릴게요. {q_text(q['text'])}",
        quick_replies=options,
        multi=multi,
        meta={"node_id": next_node, "section": section, "answers": answers},
    )
