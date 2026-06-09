"""Langfuse 관측성 — LangChain CallbackHandler 단일 소스.

모든 LLM 호출부(`ai.agents.base`, `app.api.chat`, `app.api.emr`)가
여기서 받은 핸들러를 `ainvoke(config={"callbacks": [...]})` 에 넘겨
latency·토큰·트레이스를 Langfuse 로 전송한다.

자격증명은 환경변수(LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY /
LANGFUSE_BASE_URL)에서 자동으로 읽는다 — 코드에 키를 두지 않는다.
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_langfuse_handler() -> "CallbackHandler":
    """프로세스당 1개의 CallbackHandler 를 재사용한다(import 시점 부작용 회피)."""
    from langfuse.langchain import CallbackHandler

    return CallbackHandler()


# ── 평가 점수(Score) 전송 — judge/validation 결과를 Langfuse 대시보드에 ──────────
# 지금까지 audit.log에만 남던 LLM-as-judge·규칙 검증 점수를 Langfuse trace에 붙여
# UI(대시보드)에서 추세를 본다. 자격증명 없거나 오류면 조용히 통과한다(fail-open) —
# 관측성 때문에 평가 파이프라인이 절대 깨지지 않도록.


def _get_client():
    from langfuse import get_client

    return get_client()


# score_trace 가 만든 evaluator trace 가 '실제(활성)'인지 표시 — push_scores 가 읽어
# Langfuse 비활성(키 없음)일 때 점수 전송을 건너뛴다(로그 노이즈 방지).
_trace_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_langfuse_trace_active", default=False
)


def _is_real_trace_id(trace_id: object) -> bool:
    """no-op(비활성) span 은 trace_id 가 전부 0 → 실제 trace 가 아님."""
    text = str(trace_id or "")
    return bool(text) and set(text) != {"0"}


@contextmanager
def score_trace(name: str):
    """평가 작업을 Langfuse 'evaluator' trace로 감싼다.

    이 컨텍스트 안에서:
      - call_openai(LLM) 호출은 같은 trace의 generation 으로 nested 되고,
      - push_scores() 로 보낸 점수가 그 trace 에 붙는다.
    Langfuse 미설정/오류면 span 없이 그대로 통과한다(fail-open). 항상 1회만 yield.
    """
    cm = None
    token = None
    try:
        cm = _get_client().start_as_current_observation(name=name, as_type="evaluator")
        span = cm.__enter__()
        token = _trace_active.set(_is_real_trace_id(getattr(span, "trace_id", None)))
    except Exception as exc:  # noqa: BLE001 — 관측성 실패는 평가를 막지 않는다
        logger.debug("[Langfuse] score_trace 진입 실패(무시): %s", exc)
        cm = None
    try:
        yield
    finally:
        if token is not None:
            _trace_active.reset(token)
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[Langfuse] score_trace 종료 실패(무시): %s", exc)


def push_scores(
    numeric: dict[str, float | int | None] | None = None,
    categorical: dict[str, str | None] | None = None,
) -> None:
    """현재 Langfuse trace 에 점수를 첨부한다(score_trace 컨텍스트 안에서 호출).

    numeric: NUMERIC 점수(품질·완전성 등), categorical: CATEGORICAL 점수(verdict·status 등).
    None 값은 건너뛴다. Langfuse 비활성이면 조용히 통과(fail-open).
    """
    if not _trace_active.get():
        return  # Langfuse 비활성 — score_current_trace 가 'no active span' 로그를 뱉지 않도록 스킵

    try:
        client = _get_client()
    except Exception as exc:  # noqa: BLE001
        logger.debug("[Langfuse] push_scores client 실패(무시): %s", exc)
        return

    for key, value in (numeric or {}).items():
        if not isinstance(value, (int, float)):
            continue
        try:
            client.score_current_trace(name=key, value=float(value), data_type="NUMERIC")
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Langfuse] score(%s) 실패(무시): %s", key, exc)

    for key, value in (categorical or {}).items():
        if not value:
            continue
        try:
            client.score_current_trace(name=key, value=str(value), data_type="CATEGORICAL")
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Langfuse] score(%s) 실패(무시): %s", key, exc)
