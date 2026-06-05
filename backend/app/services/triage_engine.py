"""Triage Engine — vet_triage.json decision tree 결정론 walker + scoring.

`triage_kb.load_triage_kb()` 위에 구축한다.

설계(결정론 walker 주도):
- 노드(질문)별 JSON 질문 + pill을 제시하고, pill 선택을 따라 `next`로 이동한다.
- 종료 노드(`is_final` 또는 next 없음, red_flag pill)에 도달하면 scoring_engine 규칙으로
  urgency를 결정론적으로 산출한다(LLM 무관).
- LLM은 자유텍스트→pill 분류에만 쓰이며(chat.py), 엔진 자체는 순수 결정론이다.

scoring_engine(vet_triage.json):
  score = Σ pill.urgency_score + 선택된 timing pill.urgency_modifier + 종 보정
  종 보정: cat & section∈{RESPIRATORY,CARDIAC,UNABLE_TO_WALK} +1 / cat & UROGENITAL & male +2
  임계: red_flag→RED, ≥10 RED, ≥7 ORANGE, ≥4 YELLOW, else GREEN
"""
from __future__ import annotations

import re
from functools import lru_cache

from .triage_kb import load_triage_kb

START_NODE = "Q_INIT_SYMPTOM"  # species는 펫 프로필에서 선주입 → Q_INIT_SPECIES 스킵

# VTL 4단계 → 기존 urgency_level_num(1~5)/라벨 매핑
_URGENCY_MAP = {
    "RED": (1, "즉시"),
    "ORANGE": (2, "응급"),
    "YELLOW": (3, "긴급"),
    "GREEN": (4, "준긴급"),
}

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """공백 제거 + 소문자화(라벨 정확매칭용)."""
    return _WS_RE.sub("", (text or "").strip().lower())


@lru_cache(maxsize=1)
def _node_index() -> dict:
    """node_id → {question dict + section_id} 평탄화 인덱스(initial + sections)."""
    kb = load_triage_kb()
    index: dict[str, dict] = {}

    for q in kb.get("initial_questions", []):
        index[q["id"]] = {**q, "section_id": None}

    for section in kb.get("sections", []):
        sid = section.get("id")
        for q in section.get("questions", []):
            index[q["id"]] = {**q, "section_id": sid}

    return index


@lru_cache(maxsize=1)
def _section_entry_map() -> dict:
    """section_id → 첫 질문 id (예: RESPIRATORY → Q_RESP_01)."""
    kb = load_triage_kb()
    out: dict[str, str] = {}
    for section in kb.get("sections", []):
        qs = section.get("questions", [])
        if qs:
            out[section.get("id")] = qs[0]["id"]
    return out


def get_node(node_id: str) -> dict | None:
    """node_id의 질문 dict(+section_id) 반환."""
    return _node_index().get(node_id)


def section_label(section_id: str | None) -> str:
    """section_id → 한국어 라벨(chief_complaint용)."""
    if not section_id:
        return "증상 상담"
    for section in load_triage_kb().get("sections", []):
        if section.get("id") == section_id:
            return section.get("label", section_id)
    return section_id


def visible_pills(node_id: str, species: str | None = None) -> list[dict]:
    """현재 노드에서 보여줄 pill 목록(종 한정 pill은 종 불일치 시 제외)."""
    node = get_node(node_id)
    if not node:
        return []
    pills = []
    for p in node.get("pills", []):
        sp = p.get("species")
        if sp and species and sp != species:
            continue
        pills.append(p)
    return pills


def pill_labels(node_id: str, species: str | None = None) -> list[str]:
    """quick_replies로 내려줄 pill 라벨 목록."""
    return [p["label"] for p in visible_pills(node_id, species)]


def is_multi(node_id: str) -> bool:
    node = get_node(node_id)
    return bool(node and node.get("type") == "multi")


def match_pill(node_id: str, text: str) -> dict | None:
    """현재 노드 pill 중 라벨이 일치하는 pill 반환(클릭 처리). 없으면 None."""
    norm = _normalize(text)
    if not norm:
        return None
    node = get_node(node_id)
    for p in (node.get("pills", []) if node else []):
        nl = _normalize(p.get("label", ""))
        if nl and (nl == norm or nl in norm or norm in nl):
            return p
    return None


def advance(node_id: str, selected: list[dict]) -> str | None:
    """선택된 pill(들)을 반영해 다음 노드 id를 결정. None이면 종료.

    - Q_INIT_SYMPTOM: 첫 선택 증상의 next_section → 섹션 첫 질문.
    - red_flag pill 선택: 즉시 종료(None).
    - 그 외: pill.next(있으면) → 없으면 question.next → 없으면 종료.
    """
    if not selected:
        return None

    if node_id == START_NODE:
        first = selected[0]
        section = first.get("next_section") or first.get("value")
        return _section_entry_map().get(section)

    if any(p.get("red_flag") for p in selected):
        return None

    node = get_node(node_id) or {}
    for p in selected:
        if p.get("next"):
            return p["next"]
    return node.get("next")


def is_terminal(node_id: str, selected: list[dict]) -> bool:
    """이 선택으로 문진이 종료되는지(다음 노드 없음)."""
    node = get_node(node_id) or {}
    if node.get("is_final"):
        return True
    return advance(node_id, selected) is None


def compute_urgency(answers: list[dict], species: str | None, section: str | None,
                    gender: str | None = None) -> dict:
    """누적 answers로 scoring_engine 규칙에 따라 urgency 산출.

    반환: {urgency, urgency_level_num, urgency_level, total_score, red_flag}
    """
    red_flag = any(p.get("red_flag") for p in answers)

    score = 0
    for p in answers:
        score += p.get("urgency_score") or 0
        score += p.get("urgency_modifier") or 0  # timing pill

    if species == "cat":
        if section in ("RESPIRATORY", "CARDIAC", "UNABLE_TO_WALK"):
            score += 1
        # 중성화 정보 부재 시 보수적으로 수컷을 intact로 간주(+2)
        if section == "UROGENITAL" and gender == "male":
            score += 2

    if red_flag or score >= 10:
        urgency = "RED"
    elif score >= 7:
        urgency = "ORANGE"
    elif score >= 4:
        urgency = "YELLOW"
    else:
        urgency = "GREEN"

    num, label = _URGENCY_MAP[urgency]
    return {
        "urgency": urgency,
        "urgency_level_num": num,
        "urgency_level": label,
        "total_score": score,
        "red_flag": red_flag,
    }


def to_collected_info(answers: list[dict], species: str | None, section: str | None,
                      gender: str | None = None) -> dict:
    """walk 결과를 기존 triage collected_info 스키마로 변환."""
    u = compute_urgency(answers, species, section, gender)

    symptom_pills = [p for p in answers if p.get("urgency_score")]
    symptom_pills.sort(key=lambda p: p.get("urgency_score", 0), reverse=True)
    keywords = [p["label"] for p in symptom_pills][:4]

    clinical: list[str] = []
    for p in answers:
        for kw in p.get("keywords", []) or []:
            if kw not in clinical:
                clinical.append(kw)

    red_flags = [
        p.get("vtl_discriminator_id") or p.get("value")
        for p in answers if p.get("red_flag")
    ]

    label = section_label(section)
    return {
        "is_triage_complete": True,
        "urgency_level": u["urgency_level"],
        "urgency_level_num": u["urgency_level_num"],
        "vtl_basis": f"decision_tree {section} score={u['total_score']} → {u['urgency']}",
        "red_flags": red_flags,
        "is_initial_visit": True,
        "chief_complaint": label,
        "symptom_keywords": keywords or [label],
        "suspected_diseases": clinical[:3],
        "symptom_summary": f"{label}: " + ", ".join(keywords) if keywords else label,
        "recommended_action": "내원 권장",
        "need_followup": u["urgency_level_num"] <= 2,
        "followup_reason": (f"응급도 {u['urgency_level']}" if u["urgency_level_num"] <= 2 else None),
    }
