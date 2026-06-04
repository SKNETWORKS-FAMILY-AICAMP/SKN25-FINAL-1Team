"""Langfuse 관측성 — LangChain CallbackHandler 단일 소스.

모든 LLM 호출부(`ai.agents.base`, `app.api.chat`, `app.api.emr`)가
여기서 받은 핸들러를 `ainvoke(config={"callbacks": [...]})` 에 넘겨
latency·토큰·트레이스를 Langfuse 로 전송한다.

자격증명은 환경변수(LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY /
LANGFUSE_BASE_URL)에서 자동으로 읽는다 — 코드에 키를 두지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler


@lru_cache(maxsize=1)
def get_langfuse_handler() -> "CallbackHandler":
    """프로세스당 1개의 CallbackHandler 를 재사용한다(import 시점 부작용 회피)."""
    from langfuse.langchain import CallbackHandler

    return CallbackHandler()
