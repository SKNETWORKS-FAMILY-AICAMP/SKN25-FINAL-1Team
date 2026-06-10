"""[정량 평가 3 · LIVE] 실제 지연/비용 측정 — mock 아님.

이전(mock) 버전은 time.sleep 으로 지연을 '연기'하고 토큰을 하드코딩했다 → 무의미.
이 버전은 *실제 OpenAI 호출의 wall-clock* 과 *응답 usage 의 실제 토큰* 으로 단가를 계산한다.

기본 SKIP, `RUN_LIVE_EVAL=1` 일 때만 실행(비용). RAG 단계는 DB(pgvector)가 있을 때만
측정하고, 없으면 LLM 단계만 측정한다(graceful).

산출물: backend/eval_latency_cost.json
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # run_eval 직접 실행(호스트 파이썬, pytest 미설치) 대비
    class _PytestShim:
        class mark:
            @staticmethod
            def skipif(*a, **k):
                def deco(fn):
                    return fn
                return deco
    pytest = _PytestShim()  # type: ignore

_OUT = Path(__file__).resolve().parents[2] / "eval_latency_cost.json"

# OpenAI 공개 단가(USD / 1M tokens). 모델 추가 시 갱신.
# 출처: developers.openai.com/api/docs/pricing (2026-06 확인).
_PRICING = {
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},   # 운영 기본 모델(backend/.env)
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}


def _cost_per_1000(model: str, in_tok: int, out_tok: int) -> float | None:
    p = _PRICING.get(model)
    if not p:
        return None
    one = in_tok * p["input"] / 1_000_000 + out_tok * p["output"] / 1_000_000
    return round(one * 1000, 4)


# 반복 횟수(단발 측정의 run간 변동을 통계로 흡수). 환경변수로 조정.
_LLM_REPEAT = int(os.environ.get("EVAL_LLM_REPEAT", "20"))
_RAG_REPEAT = int(os.environ.get("EVAL_RAG_REPEAT", "20"))


def _stats(xs: list[float]) -> dict:
    """median / p95 / min / max / mean(소수4) — 단발값 대신 분포로 보고."""
    if not xs:
        return {}
    s = sorted(xs)
    n = len(s)
    p95 = s[min(n - 1, int(round(0.95 * (n - 1))))]
    return {
        "n": n,
        "median": round(s[n // 2], 4),
        "p95": round(p95, 4),
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "mean": round(sum(s) / n, 4),
    }


async def _measure_llm() -> dict:
    """차트 초안 수준 LLM 호출을 _LLM_REPEAT회 반복 → 지연/비용 분포(중앙값·p95)."""
    from openai import AsyncOpenAI

    from app.core.config import settings

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    model = settings.OPENAI_MODEL or "gpt-4o-mini"
    prompt = (
        "다음 문진을 SOAP 차트 초안으로 구조화하라(JSON). "
        "강아지, 3세, 어제부터 구토 3회·설사·식욕저하, 발현 1일 전."
    )

    lats: list[float] = []
    in_toks: list[int] = []
    out_toks: list[int] = []
    costs: list[float] = []
    for _ in range(_LLM_REPEAT):
        start = time.perf_counter()
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_completion_tokens=400,
            response_format={"type": "json_object"},
        )
        lats.append(time.perf_counter() - start)
        u = resp.usage
        in_toks.append(u.prompt_tokens)
        out_toks.append(u.completion_tokens)
        c = _cost_per_1000(model, u.prompt_tokens, u.completion_tokens)
        if c is not None:
            costs.append(c)

    return {
        "step": "llm_chart_draft", "model": model, "repeat": _LLM_REPEAT,
        "latency_sec": _stats(lats),
        "input_tokens": _stats([float(x) for x in in_toks]),
        "output_tokens": _stats([float(x) for x in out_toks]),
        "cost_per_1000_usd": _stats(costs) if costs else None,
    }


async def _measure_rag() -> dict | None:
    """RAG 검색(임베딩+pgvector)을 _RAG_REPEAT회 반복 → 지연 분포. DB 없으면 skipped."""
    try:
        from app.db.session import AsyncSessionLocal
        from ai.triage.rag import search_similar_triage_cases

        lats: list[float] = []
        last = []
        for _ in range(_RAG_REPEAT):
            start = time.perf_counter()
            async with AsyncSessionLocal() as db:
                last = await search_similar_triage_cases(db, "구토하고 설사해요", top_k=3, expand_query=False)
            lats.append(time.perf_counter() - start)
        return {"step": "rag_search", "repeat": _RAG_REPEAT, "latency_sec": _stats(lats),
                "results": len(last),
                "top_similarity": round(last[0].similarity, 4) if last else None}
    except Exception as exc:  # noqa: BLE001 — DB 미가동 등은 측정 생략
        return {"step": "rag_search", "skipped": str(exc)[:120]}


async def _run() -> dict:
    logs = []
    rag = await _measure_rag()
    if rag:
        logs.append(rag)
    logs.append(await _measure_llm())
    return {"logs": logs}


@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVAL") != "1",
                    reason="LIVE 평가: RUN_LIVE_EVAL=1 일 때만 실행(OpenAI 비용)")
def test_latency_and_cost_measured():
    report = asyncio.run(_run())
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    llm = next((x for x in report["logs"] if x["step"] == "llm_chart_draft"), None)
    assert llm and llm["latency_sec"]["median"] > 0 and llm["input_tokens"]["median"] > 0


if __name__ == "__main__":
    rep = asyncio.run(_run())
    _OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in rep["logs"]:
        print(x)
    print(f"→ {_OUT}")
