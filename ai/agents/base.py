"""공용 LLM 비동기 호출 함수 — 모든 에이전트가 공유합니다.

LangChain(ChatOpenAI) 기반. 관측성(Langfuse)은 이후 단계에서
LangChain 콜백 핸들러로 부착하므로 여기엔 두지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import logging

from langchain_openai import ChatOpenAI

from ai.observability import get_langfuse_handler

logger = logging.getLogger(__name__)

# 네트워크 지연·일시 오류·깨진 JSON에 대비한 호출 견고성 파라미터.
# 무한 대기(SDK 기본 600s)를 막고, 일시 오류는 1회 재시도한다.
OPENAI_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 2  # 최초 + 재시도 1회

# (model, temperature, max_tokens, json_mode) → ChatOpenAI 캐시.
# 호출마다 httpx 클라이언트를 새로 만드는 비용을 피한다.
_clients: dict[tuple, ChatOpenAI] = {}


def _get_client(model: str, temperature: float, max_tokens: int, json_mode: bool) -> ChatOpenAI:
    key = (model, temperature, max_tokens, json_mode)
    client = _clients.get(key)
    if client is None:
        from app.core.config import settings

        # gpt-5 계열은 max_tokens 대신 max_completion_tokens 를 요구한다.
        # LangChain(구버전)의 자동 max_tokens 매핑을 우회하려고 model_kwargs 로
        # 원하는 파라미터를 OpenAI 요청 바디에 그대로 전달한다.
        model_kwargs: dict = {"max_completion_tokens": max_tokens}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}

        client = ChatOpenAI(
            model=model,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT_S,
            max_retries=0,  # 재시도는 아래 call_openai 루프에서 직접 처리
            model_kwargs=model_kwargs,
        )
        _clients[key] = client
    return client


def _parse_json(text: str) -> dict:
    """```json 래핑 제거 후 파싱."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(clean)


async def call_openai(
    messages: list[dict],
    system: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1200,
    json_mode: bool = True,
    temperature: float = 0.3,
    agent: str = "unknown",
) -> dict | str:
    """LangChain ChatOpenAI 비동기 호출.

    - timeout(30s) + 1회 재시도로 일시 오류·깨진 JSON에 대응한다.
    - json_mode=True면 파싱된 dict를 반환한다.
    - 모든 시도가 실패하면 마지막 예외를 raise → 호출부(에이전트 러너)가
      격리/로깅하도록 둔다. (상위에서 fallback 처리)
    - agent: Langfuse 트레이스 이름(run_name)으로 쓰여 에이전트별 구분이 된다.
    """
    client = _get_client(model, temperature, max_tokens, json_mode)
    lc_messages = [{"role": "system", "content": system}, *messages]

    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.ainvoke(
                lc_messages,
                config={"run_name": agent, "callbacks": [get_langfuse_handler()]},
            )
            text = response.content if isinstance(response.content, str) else str(response.content)
            return _parse_json(text) if json_mode else text
        except (json.JSONDecodeError, asyncio.TimeoutError, Exception) as exc:
            last_exc = exc
            logger.warning(
                "[LLM] 호출 실패 (attempt %d/%d) model=%s: %s",
                attempt, MAX_ATTEMPTS, model, exc,
            )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * attempt)  # 짧은 백오프 후 재시도
    # 재시도까지 실패 — 호출부가 처리하도록 예외 전파
    raise last_exc if last_exc else RuntimeError("LLM 호출 실패")


async def call_openai_once(
    user_prompt: str,
    system: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1200,
    json_mode: bool = True,
    agent: str = "unknown",
) -> dict | str:
    return await call_openai(
        [{"role": "user", "content": user_prompt}],
        system,
        model=model,
        max_tokens=max_tokens,
        json_mode=json_mode,
        agent=agent,
    )
