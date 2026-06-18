"""라우팅 — "이 발화는 누가 답할지" 결정. 담당: 리드.
설계서 §4 / AGENT_SPECS '공통 동작 규칙'. 규칙 먼저(결정론) → LLM 분류(보조).
"""
from __future__ import annotations

from .contracts import Flow, Phase, SessionContext

# phase별 후보 노드 (설계서 §4 1단계)
CANDIDATES: dict[Phase, set[str]] = {
    Phase.PRE_BOOKING: {"reception", "triage", "schedule"},
    Phase.BOOKED: {"reception", "followup_filter"},
    Phase.CLOSED: {"reception"},  # CLOSED서도 병원정보 응대는 함(경과 입력만 마감)
}


def route(ctx: SessionContext) -> str:
    """반환: 처리 노드 이름 {reception|triage|schedule|followup_filter|redirect}.

    1) sticky 가드: 문진 중이면 문진 유지 (명백한 이탈만 빠져나감 — TODO)
    2) phase로 후보 축소
    3) TODO(리드): 후보가 여럿이면 call_llm_structured로 인텐트 분류
         actionable→해당 노드 / pet_general→reception / unrelated→redirect
    지금은 안전한 기본값만 반환하는 stub.
    """
    # 2단계 sticky (설계서 §4 / §4.1)
    if ctx.active_flow == Flow.TRIAGING:
        return "triage"
    # 3단계 자리 — 지금은 phase 기본값
    if ctx.phase == Phase.BOOKED:
        return "followup_filter"
    return "reception"  # PRE_BOOKING / CLOSED 기본 (LLM 분류 붙기 전 임시)
