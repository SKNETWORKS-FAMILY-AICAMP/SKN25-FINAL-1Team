"""모델 후보 비교 — 1단계 스모크/비용/지연 측정 (에이전트 미구동, 안전).

목적:
  "OPENAI_MODEL 을 무엇으로 둘지"를 감이 아니라 실측으로 정하기 위한 1차 스크리닝.
  실제 Triage/Chart/Schedule 에이전트는 건드리지 않고(=리팩토링 영역 무관),
  대표 트리아지 프롬프트를 후보 모델들에 직접 던져 아래를 비교한다:
    · 존재/응답 여부   — 잘못된 모델명/권한없음이면 여기서 바로 드러남
    · JSON 포맷 안정성 — structured 출력 요구를 모델이 지키는 비율
    · 지연(latency)    — 챗봇 UX 직결 (p50/p95)
    · 토큰 사용량      — 비용 추정 입력 (가격은 --prices 로 직접 주입; 임의값 안 박음)

입력은 실제 벤치(vet_eval_dataset.json)의 보호자 대화에서 N건을 샘플링해 대표성을 확보한다.

  ⚠️ 품질(응급 red-flag 재현율·urgency 정확도·flawed 적발률 등) 채점은 이 스크립트 범위 밖이다.
     그건 2단계 run_vet_eval.py(=에이전트 구동 + gold 채점)가 담당한다.

실행:
  # 현재 .env 의 OPENAI_API_KEY 사용. 후보 모델은 쉼표로.
  python backend/scripts/eval_models.py \
      --models gpt-5.4-mini,gpt-4o-mini \
      --n 20 --concurrency 4 \
      --prices '{"gpt-5.4-mini":[0.15,0.60],"gpt-4o-mini":[0.15,0.60]}' \
      --out /tmp/model_eval.json

  # --prices 는 {모델: [입력$/1M토큰, 출력$/1M토큰]} — 실제 요금표를 직접 채운다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # backend (app.* 용)

DATASET = HERE.parent / "data" / "validation" / "vet_eval_dataset.json"

SYSTEM_PROMPT = (
    "당신은 동물병원 사전 문진 트리아지 보조입니다. 보호자 대화를 읽고 "
    "응급도와 위험신호, 의심질환을 판단합니다. 반드시 아래 JSON 스키마로만 답하세요:\n"
    '{"urgency_level_num": 1~5 정수, "red_flags": [문자열], "suspected_diseases": [문자열]}\n'
    "urgency_level_num 은 1(경미)~5(즉시 응급). 설명/코드펜스 없이 JSON 객체만 출력."
)


def _load_samples(n: int) -> list[str]:
    """벤치의 보호자 발화(user 턴)를 케이스별로 합쳐 입력 텍스트 N건을 만든다."""
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    samples: list[str] = []
    for c in cases[:n]:
        msgs = (c.get("input") or {}).get("messages") or []
        user_turns = [m.get("content", "") for m in msgs if m.get("role") == "user"]
        text = " ".join(t.strip() for t in user_turns if t.strip())
        if text:
            samples.append(text)
    return samples


async def _one_call(client, model: str, user_text: str) -> dict:
    """단일 호출 — 지연/토큰/JSON성공 측정. 예외는 결과 dict 로 흡수."""
    t0 = time.perf_counter()
    base_kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_object"},
    )
    try:
        try:
            # 결정론적 비교를 위해 temperature=0 우선 시도.
            resp = await client.chat.completions.create(temperature=0, **base_kwargs)
        except Exception as e:
            # 추론형 모델(gpt-5.5 등)은 temperature 고정값(1)만 허용 → 빼고 재시도.
            if "temperature" in str(e).lower():
                resp = await client.chat.completions.create(**base_kwargs)
            else:
                raise
        dt = time.perf_counter() - t0
        content = resp.choices[0].message.content or ""
        json_ok = True
        try:
            parsed = json.loads(content)
            json_ok = isinstance(parsed, dict) and "urgency_level_num" in parsed
        except json.JSONDecodeError:
            json_ok = False
        usage = resp.usage
        return {
            "ok": True,
            "json_ok": json_ok,
            "latency": dt,
            "tokens_in": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "tokens_out": getattr(usage, "completion_tokens", 0) if usage else 0,
        }
    except Exception as e:  # 모델 없음/권한/레이트리밋 등 — 여기서 드러난다
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "latency": time.perf_counter() - t0}


async def _eval_model(client, model: str, samples: list[str], concurrency: int) -> dict:
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(text: str) -> dict:
        async with sem:
            return await _one_call(client, model, text)

    results = await asyncio.gather(*[_guarded(s) for s in samples])
    ok = [r for r in results if r["ok"]]
    errs = [r for r in results if not r["ok"]]
    lats = [r["latency"] for r in ok]
    agg = {
        "model": model,
        "n": len(results),
        "ok": len(ok),
        "errors": len(errs),
        "first_error": errs[0]["error"] if errs else None,
        "json_ok_rate": round(sum(r["json_ok"] for r in ok) / len(ok), 3) if ok else 0.0,
        "p50_latency": round(statistics.median(lats), 2) if lats else None,
        "p95_latency": round(sorted(lats)[int(len(lats) * 0.95) - 1], 2) if len(lats) >= 2 else (round(lats[0], 2) if lats else None),
        "mean_tokens_in": round(statistics.mean(r["tokens_in"] for r in ok), 1) if ok else 0,
        "mean_tokens_out": round(statistics.mean(r["tokens_out"] for r in ok), 1) if ok else 0,
    }
    return agg


def _est_cost(agg: dict, prices: dict) -> str:
    p = prices.get(agg["model"])
    if not p or not agg["ok"]:
        return "n/a"
    pin, pout = p
    per_call = (agg["mean_tokens_in"] * pin + agg["mean_tokens_out"] * pout) / 1_000_000
    return f"${per_call*1000:.4f}/1k호출"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="쉼표구분 후보 모델 ID")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--prices", default="{}", help='{"model":[in$/1M,out$/1M]} 실제 요금')
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from openai import AsyncOpenAI
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY 가 .env 에 없습니다.", file=sys.stderr)
        sys.exit(1)

    prices = json.loads(args.prices)
    samples = _load_samples(args.n)
    if not samples:
        print("벤치 샘플을 못 불러왔습니다.", file=sys.stderr)
        sys.exit(1)

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print(f"# 후보 {len(models)}개 × 샘플 {len(samples)}건\n")
    aggs = []
    for m in models:
        agg = await _eval_model(client, m, samples, args.concurrency)
        aggs.append(agg)

    # 표 출력
    cols = ["model", "ok/n", "json_ok", "p50(s)", "p95(s)", "tok_in", "tok_out", "est_cost", "note"]
    print(" | ".join(cols))
    print("-|-".join("-" * len(c) for c in cols))
    for a in aggs:
        print(" | ".join([
            a["model"],
            f'{a["ok"]}/{a["n"]}',
            str(a["json_ok_rate"]),
            str(a["p50_latency"]),
            str(a["p95_latency"]),
            str(a["mean_tokens_in"]),
            str(a["mean_tokens_out"]),
            _est_cost(a, prices),
            (a["first_error"] or "")[:40],
        ]))

    if args.out:
        Path(args.out).write_text(json.dumps(aggs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
