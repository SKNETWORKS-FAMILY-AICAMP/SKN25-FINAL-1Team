"""LangGraph 오케스트레이션 — 에이전트 파이프라인을 StateGraph로 구성.

비동기 이벤트별 그래프(각 그래프는 BackgroundTask 안에서 `await graph.ainvoke(state)`):
- post_booking_graph: chart → validation → (조건부) judge   [예약확정 후 백그라운드]

노드는 ai.tasks.RUNNERS(monitor_agent 관측성 포함)를 호출하고 _task_store를 갱신한다.
각 노드는 예외를 격리해 한 단계 실패가 다음 단계를 막지 않는다(기존 동작 보존).
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ai.tasks import RUNNERS, _task_store, save_result

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("medipaw.audit")

# Judge(LLM-as-a-Judge) QA 샘플링 비율: emrid % N == 0 일 때만 실행해 비용을 제어한다.
JUDGE_SAMPLE_RATE = 5


class PostBookingState(TypedDict, total=False):
    """예약확정 후 chart→validation→judge 파이프라인 상태."""
    emrid: int
    scheduleid: int
    user_id: int
    chart_payload: dict
    validation_payload: dict
    judge_payload: dict
    chart_task_id: str
    validation_task_id: str
    judge_task_id: str
    chart_result: Any
    validation_result: Any
    judge_result: Any


def _updater(task_id: str):
    def update_step(step: str) -> None:
        if task_id in _task_store:
            _task_store[task_id]["step"] = step
    return update_step


async def _chart_node(state: PostBookingState) -> dict:
    emrid, scheduleid = state["emrid"], state["scheduleid"]
    tid = state["chart_task_id"]
    _task_store[tid] = {"status": "running", "step": "차트 초안 생성 중..."}
    try:
        result = await RUNNERS["chart"](state["chart_payload"], _updater(tid), emrid, scheduleid)
        _task_store[tid] = {"status": "done", "result": result}
        await save_result("chart", result, emrid, scheduleid, state["user_id"])
        logger.info(f"[Graph] chart done emrid={emrid}")
        return {"chart_result": result}
    except Exception as e:
        logger.error(f"[Graph] chart failed emrid={emrid}: {e}", exc_info=True)
        _task_store[tid] = {"status": "error", "detail": str(e)}
        return {"chart_result": None}


async def _validation_node(state: PostBookingState) -> dict:
    emrid, scheduleid = state["emrid"], state["scheduleid"]
    tid = state["validation_task_id"]
    _task_store[tid] = {"status": "running", "step": "품질·안전성 검증 중..."}
    # Validation B(문진↔차트 일관성)는 차트 초안을 비교하므로 chart_result를 주입.
    payload = {**state["validation_payload"], "chart_result": state.get("chart_result")}
    try:
        result = await RUNNERS["validation"](payload, _updater(tid), emrid, scheduleid)
        _task_store[tid] = {"status": "done", "result": result}
        await save_result("validation", result, emrid, scheduleid, state["user_id"])
        logger.info(f"[Graph] validation done emrid={emrid} overall={result.get('overall')}")
        return {"validation_result": result}
    except Exception as e:
        logger.error(f"[Graph] validation failed emrid={emrid}: {e}", exc_info=True)
        _task_store[tid] = {"status": "error", "detail": str(e)}
        return {"validation_result": None}


async def _judge_node(state: PostBookingState) -> dict:
    """운영 품질 모니터링(환자 안전 검증 아님). audit log만, DB 저장 없음."""
    emrid, scheduleid = state["emrid"], state["scheduleid"]
    result = None
    try:
        result = await RUNNERS["judge"](state["judge_payload"], lambda _: None, emrid, scheduleid)
        audit_logger.info(
            "[JudgeAudit] emrid=%s verdict=%s scores=%s turns=%s",
            emrid,
            result.get("monitoring_verdict"),
            result.get("quality_scores"),
            result.get("turn_count"),
        )
    except Exception as exc:
        logger.warning(f"[Graph] judge audit failed emrid={emrid}: {exc}")
    return {"judge_result": result}


def _after_validation(state: PostBookingState) -> str:
    """Judge는 비용 제어를 위해 emrid 샘플링된 경우에만 실행."""
    emrid = state.get("emrid")
    if emrid is not None and emrid % JUDGE_SAMPLE_RATE == 0:
        return "judge"
    return "skip"


def _build_post_booking_graph():
    g = StateGraph(PostBookingState)
    g.add_node("chart", _chart_node)
    g.add_node("validation", _validation_node)
    g.add_node("judge", _judge_node)
    g.set_entry_point("chart")
    g.add_edge("chart", "validation")
    g.add_conditional_edges("validation", _after_validation, {"judge": "judge", "skip": END})
    g.add_edge("judge", END)
    return g.compile()


# 컴파일된 그래프(모듈 로드 시 1회). BackgroundTask에서 ainvoke로 실행.
post_booking_graph = _build_post_booking_graph()


# ── triage_complete 그래프: 문진완료 → triage요약(LLM) → schedule ──────────────
class TriageCompleteState(TypedDict, total=False):
    emrid: int
    schedule_task_id: str
    pet: dict
    collected_info: dict
    patient_context: dict
    messages: list
    schedule_result: Any


async def _triage_summary_node(state: TriageCompleteState) -> dict:
    """triage 에이전트(LLM)로 symptom_summary를 업그레이드하고 DB를 갱신한다.

    응급도/키워드 등은 엔진 결과 유지, 요약만 LLM으로. 실패해도 흐름 유지.
    """
    emrid = state["emrid"]
    ci = dict(state.get("collected_info") or {})
    try:
        res = await RUNNERS["triage"](
            {"messages": state.get("messages") or [], "collected_info": ci, "pet": state.get("pet") or {}},
            lambda _: None, emrid, None,
        )
        ci = res.get("collected_info") or ci
        summary = res.get("symptom_summary")
        if summary:
            from sqlalchemy import select as _select

            from app.db.session import AsyncSessionLocal
            from app.models.triage_result import TriageResult
            async with AsyncSessionLocal() as db:
                row = await db.execute(_select(TriageResult).where(TriageResult.emrid == emrid))
                tr = row.scalar_one_or_none()
                if tr:
                    tr.symptom_summary = summary
                    await db.commit()
                    logger.info(f"[Graph] triage summary updated emrid={emrid}")
    except Exception as e:
        logger.warning(f"[Graph] triage summary failed emrid={emrid}: {e}")
    return {"collected_info": ci}


async def _schedule_node(state: TriageCompleteState) -> dict:
    emrid = state["emrid"]
    tid = state["schedule_task_id"]
    _task_store[tid] = {"status": "running", "step": "예약 슬롯 계산 중..."}
    try:
        payload = {
            "pet": state.get("pet") or {},
            "triage_info": state.get("collected_info") or {},
            "triage_result": state.get("collected_info") or {},
            "patient_context": state.get("patient_context"),
            "existing_bookings": [],
        }
        # 플래그 ON이면 MCP 예약 오케스트레이션(booking), 아니면 기존 schedule.
        from app.core.config import settings
        agent = "booking" if settings.USE_MCP_BOOKING else "schedule"
        result = await RUNNERS[agent](payload, _updater(tid), emrid, None)
        _task_store[tid] = {"status": "done", "result": result}
        logger.info(f"[Graph] schedule done emrid={emrid}")
        return {"schedule_result": result}
    except Exception as e:
        logger.error(f"[Graph] schedule failed emrid={emrid}: {e}", exc_info=True)
        _task_store[tid] = {"status": "error", "detail": str(e)}
        return {"schedule_result": None}


def _build_triage_complete_graph():
    # triage요약(LLM)과 schedule은 독립적(요약=DB/수의사용, schedule=urgency만 사용)이라
    # 병렬 실행해 슬롯 표시 지연을 0으로 한다.
    g = StateGraph(TriageCompleteState)
    g.add_node("triage_summary", _triage_summary_node)
    g.add_node("schedule", _schedule_node)
    g.add_edge(START, "triage_summary")
    g.add_edge(START, "schedule")
    g.add_edge("triage_summary", END)
    g.add_edge("schedule", END)
    return g.compile()


triage_complete_graph = _build_triage_complete_graph()
