"""오케스트레이터 LangGraph — 한 턴의 여정을 그래프로.

build_context → route → (조건부) 담당 노드 → END
- 에이전트는 agents/REGISTRY에서 꽂힘(지금은 전부 stub).
- 라우팅은 router.route()(규칙 먼저, LLM 분류는 TODO).
설계서 §3.4 / §4 / AGENT_SPECS 공통 동작 규칙.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .contracts import AgentResult, SessionContext
from .registry import REGISTRY
from .router import route

logger = logging.getLogger(__name__)

NODES = [*REGISTRY.keys(), "redirect"]   # reception/triage/schedule/followup_filter + redirect


class OrchState(TypedDict, total=False):
    ctx: SessionContext      # 현재 상황 묶음
    target: str              # route가 고른 처리 노드
    result: AgentResult      # 담당 노드가 채우는 응답


async def _route_node(state: OrchState) -> dict:
    target = await route(state["ctx"])
    logger.info("[orch] route → %s (flow=%s phase=%s)",
                target, state["ctx"].active_flow, state["ctx"].phase)
    return {"target": target}


def _agent_node(agent):
    async def _node(state: OrchState) -> dict:
        return {"result": await agent.run(state["ctx"], {})}
    return _node


_DEFLECT = "저는 반려동물 건강·예약을 도와드려요. 증상이나 예약을 말씀해 주세요."

# 문진 흐름 밖(응대 직후·콜드 스타트 등)에서 들어온 '회상/메타 질문'을 history로 답해준다.
# 모든 대화는 저장되므로, 어디서 물어도 "방금 뭐라 했지"에 일관되게 답하게 하는 게 목적.
_RECALL_PROMPT = """너는 동물병원 상담 도우미야. 보호자의 '이번 발화'가 '우리가 나눈 대화에 대한
회상/메타 질문'(예: "방금 뭐라 했어", "내가 뭐라고 말했지", "여태 무슨 얘기 했더라")인지 판단해.

[지금까지 대화]
{convo}

[이번 발화] {msg}

- 회상/메타 질문이면: [지금까지 대화]를 근거로 보호자가 한 말을 사실대로 짧게 짚어준다(지어내기 금지). is_recall=true.
- 아니면(무관한 잡담·일반지식 등): is_recall=false (reply는 비워도 됨).

JSON으로만: {{"is_recall": true, "reply": "회상 답변(회상일 때만)"}}"""


async def _redirect_node(state: OrchState) -> dict:
    from ai.llm import call_llm_json
    ctx = state["ctx"]
    # 현재 발화(마지막 항목)는 빼고 '이전까지'의 대화만 근거로 준다.
    hist = list(ctx.history or [])
    if hist and hist[-1].get("role") == "user" and hist[-1].get("content") == ctx.user_message:
        hist = hist[:-1]
    convo = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in hist if m.get("content"))
    if convo:
        try:
            out = await call_llm_json(_RECALL_PROMPT.format(convo=convo, msg=ctx.user_message))
            if out.get("is_recall") and (out.get("reply") or "").strip():
                return {"result": AgentResult(reply=out["reply"].strip())}
        except Exception as e:
            logger.warning("[orch] redirect 회상 처리 실패: %s", e)
    return {"result": AgentResult(reply=_DEFLECT)}


def _pick(state: OrchState) -> str:
    return state["target"]


def build_orchestrator():
    g = StateGraph(OrchState)
    g.add_node("route", _route_node)
    for name, agent in REGISTRY.items():
        g.add_node(name, _agent_node(agent))
    g.add_node("redirect", _redirect_node)

    g.add_edge(START, "route")
    g.add_conditional_edges("route", _pick, {name: name for name in NODES})
    for name in NODES:
        g.add_edge(name, END)
    return g.compile()


orchestrator = build_orchestrator()


async def run_turn(ctx: SessionContext) -> AgentResult:
    """한 턴 실행 진입점 — 나중에 chat.py(send_message)가 이걸 호출."""
    out = await orchestrator.ainvoke({"ctx": ctx})
    return out["result"]
