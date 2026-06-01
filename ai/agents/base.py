"""공용 OpenAI 비동기 호출 함수 — 모든 에이전트가 공유합니다."""
from __future__ import annotations

import asyncio
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# 네트워크 지연·일시 오류·깨진 JSON에 대비한 호출 견고성 파라미터.
# 무한 대기(SDK 기본 600s)를 막고, 일시 오류는 1회 재시도한다.
OPENAI_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 2  # 최초 + 재시도 1회

# 지연 초기화 — import 시점에 settings 로드를 피함
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        from app.core.config import settings
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


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
) -> dict | str:
    """OpenAI Chat Completions 비동기 호출.

    - timeout(30s) + 1회 재시도로 일시 오류·깨진 JSON에 대응한다.
    - json_mode=True면 파싱된 dict를 반환한다.
    - 모든 시도가 실패하면 마지막 예외를 raise → 호출부(에이전트 러너)가
      격리/로깅하도록 둔다. (상위에서 fallback 처리)
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await _get_client().chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, *messages],
                response_format={"type": "json_object"} if json_mode else None,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=OPENAI_TIMEOUT_S,
            )
            text = response.choices[0].message.content or ""
            return _parse_json(text) if json_mode else text
        except (json.JSONDecodeError, asyncio.TimeoutError, Exception) as exc:
            last_exc = exc
            logger.warning(
                "[OpenAI] 호출 실패 (attempt %d/%d) model=%s: %s",
                attempt, MAX_ATTEMPTS, model, exc,
            )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * attempt)  # 짧은 백오프 후 재시도
    # 재시도까지 실패 — 호출부가 처리하도록 예외 전파
    raise last_exc if last_exc else RuntimeError("OpenAI 호출 실패")


async def call_openai_once(
    user_prompt: str,
    system: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1200,
    json_mode: bool = True,
) -> dict | str:
    return await call_openai(
        [{"role": "user", "content": user_prompt}],
        system,
        model=model,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )
