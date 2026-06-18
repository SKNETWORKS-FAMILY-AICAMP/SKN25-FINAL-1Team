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
    target = route(state["ctx"])
    logger.info("[orch] route → %s (flow=%s phase=%s)",
                target, state["ctx"].active_flow, state["ctx"].phase)
    return {"target": target}


def _agent_node(agent):
    async def _node(state: OrchState) -> dict:
        return {"result": await agent.run(state["ctx"], {})}
    return _node


async def _redirect_node(state: OrchState) -> dict:
    return {"result": AgentResult(
        reply="저는 반려동물 건강·예약을 도와드려요. 증상이나 예약을 말씀해 주세요."
    )}


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
