"""오케스트레이터 LangGraph — 한 턴의 여정을 그래프로.

build_context → route → (조건부) 담당 노드 → END
- 에이전트는 agents/REGISTRY에서 꽂힘(지금은 전부 stub).
- 라우팅은 router.route()(규칙 먼저, LLM 분류는 TODO).
설계서 §3.4 / §4 / AGENT_SPECS 공통 동작 규칙.
"""
from __future__ import annotations

from contextvars import ContextVar
import logging

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .contracts import INITIAL_TRIAGE_PILL, AgentResult, SessionContext
from .registry import REGISTRY
from .router import route

logger = logging.getLogger(__name__)

_route_trace: ContextVar[str | None] = ContextVar("orchestrator_route_trace", default=None)


def reset_route_trace() -> None:
    """Reset per-task route diagnostics before an observed turn."""
    _route_trace.set(None)


def get_route_trace() -> str | None:
    """Return the route selected in the current asyncio task."""
    return _route_trace.get()


NODES = [*REGISTRY.keys(), "redirect"]   # reception/triage/schedule/followup_filter + redirect


class OrchState(TypedDict, total=False):
    ctx: SessionContext      # 현재 상황 묶음
    target: str              # route가 고른 처리 노드
    result: AgentResult      # 담당 노드가 채우는 응답


async def _route_node(state: OrchState) -> dict:
    target = await route(state["ctx"])
    _route_trace.set(target)
    logger.info("[orch] route → %s (flow=%s phase=%s)",
                target, state["ctx"].active_flow, state["ctx"].phase)
    return {"target": target}


def _agent_node(agent):
    async def _node(state: OrchState) -> dict:
        return {"result": await agent.run(state["ctx"], {})}
    return _node


_DEFLECT = ("반려동물 증상 상담과 병원 안내를 도와드려요.\n"
            "문진 작성 후 병원 예약도 가능해요.")

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
    return {
        "result": AgentResult(
            reply=_DEFLECT,
            quick_replies=[INITIAL_TRIAGE_PILL, "궁금한 게 있어요"],
        )
    }


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


# LLM(OpenAI) 장애 등으로 한 턴 처리가 통째로 실패했을 때 보호자에게 보일 안내.
# 챗봇 추론은 LLM 없이 대체할 수 없으므로, '전면 에러' 대신 다음 행동을 안내하며 부드럽게 떨어진다.
_DEGRADED = (
    "지금 상담 응답을 불러오는 데 일시적인 문제가 있어요. 잠시 후 다시 보내주세요.\n"
    "증상이 급해 보이면 등록하신 병원으로 바로 전화해 주세요."
)


async def run_turn(ctx: SessionContext) -> AgentResult:
    """한 턴 실행 진입점 — 나중에 chat.py(send_message)가 이걸 호출."""
    try:
        out = await orchestrator.ainvoke({"ctx": ctx})
        return out["result"]
    except Exception:
        # 한 에이전트의 LLM 호출이 실패해도 스트림을 'error'로 끊지 않고, 같은 채팅 안에서
        # 재시도를 유도하는 정상 메시지로 응답한다(상태는 저장 안 되어 다음 턴에 영향 없음).
        logger.exception("[orch] run_turn 실패 — degraded 응답으로 폴백 (session=%s)", ctx.session_id)
        return AgentResult(reply=_DEGRADED)
