"""관측(Langfuse) 자리 — 지금은 무동작 stub. 담당: 리드(나중에 실제 Langfuse 연동).

validation 등에서 `score_trace(...)` / `push_scores(...)`를 호출하는데, 실제 Langfuse 연결
전까지 import 에러·실행 에러 안 나게 no-op 으로 둔다. (설계서 §9.2)
"""
from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def score_trace(name: str):
    # TODO(리드): Langfuse trace 시작/종료로 교체
    yield None


def push_scores(numeric: dict | None = None, categorical: dict | None = None) -> None:
    # TODO(리드): Langfuse에 점수 기록으로 교체
    return None
