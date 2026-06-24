import json
import os
from functools import lru_cache

import langfuse.openai  # OpenAI 클라이언트 자동 패치 — 토큰/latency 추적
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def _resolve_model() -> str:
    """모델명 단일 결정: env(OPENAI_MODEL) → backend settings 기본값 → 최후 하드코딩.

    예전엔 os.getenv 만 봐서 env 미설정 시 model=None 으로 LLM 호출이 깨질 수 있었다.
    settings import 는 standalone 실행(테스트)에서 backend 경로가 없을 수 있어 lazy + try.
    """
    model = os.getenv("OPENAI_MODEL")
    if model:
        return model
    try:
        from app.core.config import settings
        return settings.OPENAI_MODEL
    except Exception:
        return "gpt-5.4-mini"


@lru_cache(maxsize=16)
def _build_llm(model: str, temperature: float) -> ChatOpenAI:
    """(model, temperature)별 ChatOpenAI 1개를 만들어 재사용한다.

    ★ latency: 한 턴에 라우터+에이전트로 LLM을 여러 번 연달아 부르는데, 매번 새 클라이언트를
    만들면 그때마다 새 TLS 핸드셰이크가 일어난다. 클라이언트를 캐싱하면 내부 httpx 커넥션 풀이
    keep-alive로 재사용돼 호출당 수백 ms를 아낀다. 클라이언트는 호출 간 상태가 없어 공유 안전.
    (model이 런타임에 바뀔 일은 없지만, 만약을 위해 model도 캐시 키에 넣는다.)
    """
    return ChatOpenAI(model=model, temperature=temperature)


def get_llm(
    temperature: float = 0.3,
):
    return _build_llm(_resolve_model(), temperature)


async def call_llm(
    prompt: str,
    temperature: float = 0.3,
):
    from langfuse.decorators import langfuse_context

    llm = get_llm(temperature=temperature)
    response = await llm.ainvoke(prompt)

    usage = getattr(response, "usage_metadata", None) or {}
    if usage:
        langfuse_context.update_current_observation(
            usage={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
            model=_resolve_model(),
        )

    return response.content


def _coerce_json_text(text: str) -> str:
    """LLM 출력에서 JSON 본문만 뽑아낸다(코드펜스/앞뒤 잡설 제거)."""
    t = (text or "").strip()
    # ```json ... ``` 또는 ``` ... ``` 펜스 제거
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    return t


async def call_llm_json(
    prompt: str,
    temperature: float = 0,
):
    text = await call_llm(
        prompt=prompt,
        temperature=temperature,
    )

    cleaned = _coerce_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 앞뒤에 설명이 붙은 경우: 첫 '{' ~ 마지막 '}' 만 잘라 재시도
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


# 구조화 출력 — JSON 스키마로 형식·enum 강제 (누락/오염 방지)
async def call_llm_structured(
    prompt: str,
    schema: dict,
    temperature: float = 0,
):
    from langfuse.decorators import langfuse_context

    llm = get_llm(temperature=temperature)

    structured = llm.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
    result = await structured.ainvoke(prompt)

    raw = result.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    if usage:
        langfuse_context.update_current_observation(
            usage={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
            model=_resolve_model(),
        )

    return result.get("parsed")