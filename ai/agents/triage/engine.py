"""문진 판정 엔진 (디스크리미네이터 방식) — vet_triage_v3.json 기반.

점수 가산이 아니라 '디스크리미네이터 매칭'으로 등급을 정한다:
 - 추출된 variables({섹션:{변수:값}})로 각 섹션 discriminator의 when을 평가
 - when의 모든 키가 일치하면 매칭 → 매칭된 잎 중 '가장 높은 등급' 채택(RED>ORANGE>YELLOW>GREEN)
LLM은 '대화·추출'만, 등급은 여기서 결정론으로 정한다.

질문 콜엔 goal만, 추출 콜엔 variables만 노출하기 위한 헬퍼도 제공한다.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

# vet_triage_v3.json 위치 후보(실행 cwd가 backend거나 repo 루트일 수 있어 여러 곳 시도)
_CANDIDATES = [
    Path(__file__).resolve().parents[3] / "backend" / "data" / "triage" / "vet_triage_v3.json",
    Path("backend/data/triage/vet_triage_v3.json"),
    Path("data/triage/vet_triage_v3.json"),
]

_URG_NUM = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 4}
_URG_RANK = {"RED": 0, "ORANGE": 1, "YELLOW": 2, "GREEN": 3}  # 낮을수록 응급

_RECOMMENDED_ACTION = {
    "RED": "즉시 내원",
    "ORANGE": "당일 내원",
    "YELLOW": "빠른 시일 내 내원",
    "GREEN": "일반 예약(경과 관찰)",
}


@functools.lru_cache(maxsize=1)
def _kb() -> dict:
    for p in _CANDIDATES:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("vet_triage_v3.json 을 찾을 수 없습니다.")


@functools.lru_cache(maxsize=1)
def _sections() -> dict[str, dict]:
    return {s["id"]: s for s in _kb().get("sections", [])}


# ── 팀원(테스트) 요청: KB의 red flag 목록 접근자 ──
def red_flag_list() -> list[dict]:
    """RED 등급 디스크리미네이터(생명위협 즉시-응급) 목록을 반환."""
    return _kb().get("red_flags", {}).get("flags", [])


# ── 질문 콜용: goal(자연어)만 노출 ──
def section_label(section_id: str) -> str:
    return (_sections().get(section_id) or {}).get("label", section_id or "")


def section_goal(section_id: str) -> str:
    return (_sections().get(section_id) or {}).get("goal", "")


def all_section_labels() -> str:
    """섹션 식별용 id+라벨 목록(섹션 미정일 때 질문/추출이 분류하도록)."""
    return "\n".join(f"- {s['id']} ({s.get('label', '')}): {s.get('goal', '')}"
                     for s in _kb().get("sections", []))


# ── 추출 콜용: variables(enum/concept) 노출 ──
def variables_for(section_id: str) -> dict:
    """해당 섹션의 추출 변수 스키마({name:{concept,values}})."""
    return (_sections().get(section_id) or {}).get("variables", {})


def variables_reference(section_id: str) -> str:
    """추출 LLM에 줄 변수 설명 텍스트(섹션 1개)."""
    vs = variables_for(section_id)
    if not vs:
        return "(해당 섹션 변수 없음)"
    lines = []
    for name, meta in vs.items():
        vals = "|".join(meta.get("values") or [])
        lines.append(f"- {name} [{vals}]: {meta.get('concept', '')}")
    return "\n".join(lines)


# ── 판정: 디스크리미네이터 매칭 ──
def _match_section(section_id: str, values: dict) -> list[dict]:
    """한 섹션에서 when이 모두 일치하는 discriminator를 매칭."""
    sec = _sections().get(section_id) or {}
    hits = []
    for d in sec.get("discriminators") or []:
        when = d.get("when") or {}
        if when and all(values.get(k) == v for k, v in when.items()):
            hits.append({"section": section_id, "label": d.get("label"), "urgency": d.get("urgency")})
    return hits


def match(extracted: dict) -> list[dict]:
    """extracted({섹션:{변수:값}}) 전체에서 매칭된 잎 목록(응급도순 정렬)."""
    matched: list[dict] = []
    for section_id, values in (extracted or {}).items():
        if isinstance(values, dict):
            matched.extend(_match_section(section_id, values))
    matched.sort(key=lambda d: _URG_RANK.get(d.get("urgency"), 99))
    return matched


def top_urgency(matched: list[dict]) -> str:
    """매칭 잎 중 가장 높은 등급. 없으면 None(정보 부족)."""
    if not matched:
        return None
    return min((d.get("urgency") for d in matched), key=lambda u: _URG_RANK.get(u, 99))


def red_flag_labels(matched: list[dict]) -> list[str]:
    return [d["label"] for d in matched if d.get("urgency") == "RED"]


def urgency_num(u: str) -> int:
    return _URG_NUM.get(u, 4)


def recommended_action(urgency: str) -> str:
    return _RECOMMENDED_ACTION.get(urgency, _RECOMMENDED_ACTION["GREEN"])


def build_vtl_basis(matched: list[dict], urgency: str,
                    evidence: str = "", reason: str = "") -> str:
    """판정 근거(CoT): 매칭 잎(결정론) + 추출 근거 + 한 줄 임상서술."""
    if matched:
        by_label = ", ".join(f"{d['label']}({d['urgency']})" for d in matched[:6])
        head = f"매칭: {by_label} → {urgency}"
    else:
        head = f"매칭된 응급 신호 없음 → {urgency or 'GREEN'}"
    parts = [head]
    if evidence:
        parts.append(f"근거: {evidence}")
    if reason:
        parts.append(reason)
    return " | ".join(parts)
