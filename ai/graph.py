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
from ai.agents.chart import ChartAgent
from ai.agents.validation import run_validation

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
    # care_guidance 출력
    pre_visit_instructions: list
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


# 내원 전 주의사항 생성 (LLM) — duration/슬롯과 무관해 병렬 실행
async def _care_guidance_node(state: ScheduleState) -> dict:
    tips = await ScheduleAgent().care_guidance(state.get("triage") or {})
    return {"pre_visit_instructions": tips}


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
    g.add_node("care_guidance", _care_guidance_node)
    # 본 흐름: duration → 슬롯 추천
    g.add_edge(START, "estimate_duration")
    g.add_edge("estimate_duration", "recommend_slots")
    g.add_edge("recommend_slots", END)
    # 병렬: 주의사항은 triage만 있으면 되므로 동시에 생성(슬롯 지연 없음)
    g.add_edge(START, "care_guidance")
    g.add_edge("care_guidance", END)
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
        "pre_visit_instructions": final.get("pre_visit_instructions") or [],
    }


# ── post_booking 그래프: 예약 확정 후 백그라운드 (현재 chart 단독, 추후 validation/judge 확장) ──
class PostBookingState(TypedDict, total=False):
    chart_payload: dict
    chart_result: dict
    validation_result: dict


# 차트 작성 노드 (LLM, 예외 격리)
async def _chart_node(state: PostBookingState) -> dict:
    payload = state.get("chart_payload") or {}
    try:
        result = await ChartAgent().generate(
            pet=payload.get("pet") or {},
            triage=payload.get("triage_result") or payload.get("triage_info") or {},
            patient_context=payload.get("patient_context"),
            chat_history=payload.get("chat_history") or [],
            rag_context=payload.get("rag_context"),
        )
    except Exception as e:
        logger.error("[post_booking] chart 실패: %s", e, exc_info=True)
        result = {}
    return {"chart_result": result}


# 차트 완료 후 품질 평가 노드 (결정론 + 규칙, 내부 모니터링용·예외 격리)
async def _validation_node(state: PostBookingState) -> dict:
    payload = dict(state.get("chart_payload") or {})
    payload["chart_result"] = state.get("chart_result") or {}
    try:
        result = await run_validation(
            payload, lambda _s: None, payload.get("emrid"), payload.get("scheduleid"),
        )
    except Exception as e:
        logger.error("[post_booking] validation 실패: %s", e, exc_info=True)
        result = {}
    logger.info("[post_booking] validation 완료")
    return {"validation_result": result}


# 그래프 컴파일 (모듈 로드 시 1회): chart → validation
def _build_post_booking_graph():
    g = StateGraph(PostBookingState)
    g.add_node("chart", _chart_node)
    g.add_node("validation", _validation_node)
    g.add_edge(START, "chart")
    g.add_edge("chart", "validation")
    g.add_edge("validation", END)
    return g.compile()


post_booking_graph = _build_post_booking_graph()


# 예약 확정 후 차트 파이프라인 진입점 — 백엔드 러너에서 호출
async def run_chart(chart_payload: dict) -> dict:
    final = await post_booking_graph.ainvoke({"chart_payload": chart_payload})
    return final.get("chart_result") or {}
