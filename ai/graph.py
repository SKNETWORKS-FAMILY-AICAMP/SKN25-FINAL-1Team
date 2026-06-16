"""LangGraph 오케스트레이션.

schedule_graph: 문진(triage) 완료 후 예약 단계.
  estimate_duration(LLM, 진료 예상시간) → recommend_slots(결정론, 3모드 슬롯)
슬롯은 duration 만큼 연속칸을 잡으므로 두 노드는 순차 의존 관계다.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ai.agents.schedule import ScheduleAgent

logger = logging.getLogger(__name__)


class ScheduleState(TypedDict, total=False):
    # 입력
    pet: dict
    triage: dict
    hospitalid: int | None
    doctorid: int | None
    # estimate_duration 출력
    estimated_duration_min: int
    is_initial_visit: bool
    duration_reasoning: str
    # recommend_slots 출력
    recommendations: dict


# 진료 예상시간 산정 (LLM)
async def _estimate_duration_node(state: ScheduleState) -> dict:
    result = await ScheduleAgent().estimate_duration(
        pet=state.get("pet") or {},
        triage=state.get("triage") or {},
    )
    return {
        "estimated_duration_min": result["estimated_duration_min"],
        "is_initial_visit": result["is_initial_visit"],
        "duration_reasoning": result["reasoning"],
    }


# 응급도 기반 슬롯 추천 (결정론, DB)
async def _recommend_slots_node(state: ScheduleState) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.crud.schedule import recommend_slots

    triage = state.get("triage") or {}
    duration = state.get("estimated_duration_min") or 30
    try:
        async with AsyncSessionLocal() as db:
            recs = await recommend_slots(
                db,
                urgency=triage.get("urgency"),
                duration_min=duration,
                hospitalid=state.get("hospitalid"),
                doctorid=state.get("doctorid"),
            )
    except Exception as e:
        logger.error("[schedule_graph] recommend_slots 실패: %s", e, exc_info=True)
        recs = {"bucket": "standard", "recommended": [], "earliest": [], "by_doctor": {}}
    return {"recommendations": recs}


# 그래프 컴파일 (모듈 로드 시 1회)
def _build_schedule_graph():
    g = StateGraph(ScheduleState)
    g.add_node("estimate_duration", _estimate_duration_node)
    g.add_node("recommend_slots", _recommend_slots_node)
    g.add_edge(START, "estimate_duration")
    g.add_edge("estimate_duration", "recommend_slots")
    g.add_edge("recommend_slots", END)
    return g.compile()


schedule_graph = _build_schedule_graph()


# 예약 단계 실행 진입점 — 백엔드 엔드포인트에서 호출
async def run_schedule_pipeline(
    pet: dict,
    triage: dict,
    hospitalid: int | None = None,
    doctorid: int | None = None,
) -> dict:
    final = await schedule_graph.ainvoke({
        "pet": pet,
        "triage": triage,
        "hospitalid": hospitalid,
        "doctorid": doctorid,
    })
    return {
        "estimated_duration_min": final.get("estimated_duration_min", 30),
        "is_initial_visit": final.get("is_initial_visit", True),
        "recommendations": final.get("recommendations") or {},
        "reasoning": final.get("duration_reasoning", ""),
    }
