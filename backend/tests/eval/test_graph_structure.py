"""[정량 평가 4] LangGraph 오케스트레이션 구조 검증 — LLM-free.

중간발표(master)는 프론트(useAgentPipeline.ts)가 에이전트를 순차 호출했다.
현재(main)는 백엔드 LangGraph StateGraph 두 개로 오케스트레이션한다. 이 테스트는
'그래프가 실제로 그렇게 배선됐는지'를 컴파일된 그래프에서 직접 확인한다.

  · post_booking_graph   : chart → validation → (조건부)judge   [예약확정 후]
  · triage_complete_graph: START ─∥─ triage_summary / schedule   [문진완료, 병렬]

langgraph/백엔드 의존성이 없는 환경(호스트 파이썬)에서는 자동 SKIP 된다.
스택(docker backend) 또는 의존성 설치 환경에서 `pytest`로 실행한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

graph_mod = pytest.importorskip(
    "ai.graph", reason="langgraph/백엔드 의존성 필요 — 스택 안에서 실행"
)


def _node_names(compiled) -> set[str]:
    """컴파일된 LangGraph에서 노드 이름 집합 추출(START/END 제외)."""
    g = compiled.get_graph()
    names = {n.id if hasattr(n, "id") else n for n in g.nodes}
    return {n for n in names if n not in ("__start__", "__end__", "START", "END")}


def test_post_booking_graph_wiring():
    nodes = _node_names(graph_mod.post_booking_graph)
    assert {"chart", "validation", "judge"} <= nodes, nodes
    # judge 샘플링 상수 존재(비용 제어).
    assert isinstance(graph_mod.JUDGE_SAMPLE_RATE, int) and graph_mod.JUDGE_SAMPLE_RATE >= 1


def test_triage_complete_graph_parallel():
    nodes = _node_names(graph_mod.triage_complete_graph)
    assert {"triage_summary", "schedule"} <= nodes, nodes


def test_judge_conditional_sampling():
    """judge는 emrid 샘플링(emrid % N == 0)일 때만 실행되도록 라우팅돼야 한다."""
    route = graph_mod._after_validation
    rate = graph_mod.JUDGE_SAMPLE_RATE
    assert route({"emrid": rate}) == "judge"        # 배수 → 실행
    assert route({"emrid": rate + 1}) == "skip"     # 비배수 → 생략
