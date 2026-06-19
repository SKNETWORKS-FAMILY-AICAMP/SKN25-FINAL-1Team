"""모델 품질 맞대결 — LLM 심판 블라인드 랭킹 (에이전트 미구동, 안전).

배경:
  vet_eval_dataset 의 gold urgency/red_flag 라벨이 비어 있어(=null) 자동 채점이 불가.
  실제 채점 축(completeness/defect/chart)은 validation·judge 에이전트(리팩토링 중) 필요.
  → gold 없이 "어느 모델이 더 나은 트리아지를 내나"를 비교하려고 LLM-as-judge 맞대결을 쓴다.

방식(케이스마다):
  1) 보호자-챗봇 문진 대화를 후보 모델들에 동일하게 주고 각자 트리아지 JSON 생성
  2) 후보 출력을 익명화·셔플(A/B/C…)해 심판 모델에 제시
  3) 심판이 "임상적으로 가장 적절(특히 under-triage 회피)"한 것을 1위~N위로 랭킹
  4) 승수/평균순위 집계

⚠️ 한계: 심판 자체 편향이 있고 절대 정답이 아니다(상대 비교 신호). 의료 안전(응급 누락)
   최종 판정은 사람 검수/gold 채점이 따로 필요. 이건 "후보 좁히기"용이다.

실행:
  docker cp backend/scripts/judge_models.py docker-backend-1:/app/backend/scripts/
  docker exec -w /app/backend docker-backend-1 python scripts/judge_models.py \
      --candidates gpt-5.4-mini,gpt-5.4,gpt-5.5 --judge gpt-5.5 \
      --n 16 --concurrency 4 --out /tmp/judge.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DATASET = HERE.parent / "data" / "validation" / "vet_eval_dataset.json"

TRIAGE_SYSTEM = (
    "당신은 동물병원 사전 문진 트리아지 보조입니다. 아래 보호자-챗봇 대화를 읽고 판단하세요. "
    "반드시 JSON 으로만 답하세요: "
    '{"urgency_level_num": 1~5 정수, "red_flags": [문자열], "suspected_diseases": [문자열], "reasoning": "한줄"}'
)

JUDGE_SYSTEM = (
    "당신은 수의 트리아지 품질을 심사하는 임상 심판입니다. 동일한 보호자 문진 대화에 대해 "
    "여러 후보의 트리아지 판단이 주어집니다. 가장 임상적으로 적절한 순서로 순위를 매기세요. "
    "최우선 기준은 under-triage(응급을 비응급으로 놓치는 것) 회피이고, 그다음 위험신호 포착의 정확성, "
    "의심질환의 타당성입니다. 과도한 over-triage(전부 응급 처리)도 감점합니다. "
    '반드시 JSON 으로만: {"ranking": ["A","B",...] 좋은 순서, "reason": "한줄 근거"}'
)


def _load_cases(n: int) -> list[dict]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    out = []
    for c in data.get("cases", [])[:n]:
        msgs = (c.get("input") or {}).get("messages") or []
        convo = "\n".join(
            f'{"보호자" if m.get("role")=="user" else "챗봇"}: {m.get("content","").strip()}'
            for m in msgs if m.get("content")
        )
        if convo:
            out.append({"case_id": c.get("case_id"), "convo": convo, "tier": c.get("tier")})
    return out


async def _responses_call(client, model: str, system: str, user: str) -> str:
    """Responses-API 전용 모델(pro/reasoning 계열)용 — chat/completions 미지원 모델."""
    resp = await client.responses.create(
        model=model,
        input=f"{system}\n\n{user}\n\n반드시 JSON 객체만 출력하세요.",
    )
    return getattr(resp, "output_text", None) or "{}"


async def _chat(client, model: str, system: str, user: str) -> str:
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    try:
        resp = await client.chat.completions.create(temperature=0, **kwargs)
    except Exception as e:
        msg = str(e).lower()
        if "temperature" in msg:
            resp = await client.chat.completions.create(**kwargs)
        elif "not a chat model" in msg or "v1/responses" in msg:
            # pro/reasoning 모델 → Responses API 로 우회
            return await _responses_call(client, model, system, user)
        else:
            raise
    return resp.choices[0].message.content or "{}"


def _parse_json(text: str) -> dict:
    """코드펜스/잡설 방어 JSON 파싱."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            return json.loads(t[s:e + 1])
        raise


async def _judge_case(client, case: dict, candidates: list[str], judge: str) -> dict | None:
    # 1) 후보별 트리아지 생성
    async def _gen(model):
        try:
            raw = await _chat(client, model, TRIAGE_SYSTEM, f"[대화]\n{case['convo']}")
            return model, _parse_json(raw)
        except Exception as e:
            return model, {"_error": f"{type(e).__name__}"}
    gen = dict(await asyncio.gather(*[_gen(m) for m in candidates]))
    if any("_error" in v for v in gen.values()):
        return None

    # 2) 익명화 + 셔플
    labels = list("ABCDEFGH")[:len(candidates)]
    order = candidates[:]
    random.shuffle(order)
    label_to_model = dict(zip(labels, order))
    block = "\n\n".join(
        f"[후보 {lbl}]\n" + json.dumps(gen[label_to_model[lbl]], ensure_ascii=False)
        for lbl in labels
    )
    judge_user = f"[보호자 문진 대화]\n{case['convo']}\n\n[후보 트리아지들]\n{block}"

    # 3) 심판 랭킹
    try:
        raw = await _chat(client, judge, JUDGE_SYSTEM, judge_user)
        verdict = _parse_json(raw)
        ranking_labels = [l for l in verdict.get("ranking", []) if l in label_to_model]
    except Exception:
        return None
    if not ranking_labels:
        return None
    ranking_models = [label_to_model[l] for l in ranking_labels]
    return {"case_id": case["case_id"], "ranking": ranking_models, "reason": verdict.get("reason", "")}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    random.seed(args.seed)
    from openai import AsyncOpenAI
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY 없음", file=sys.stderr); sys.exit(1)

    candidates = [m.strip() for m in args.candidates.split(",") if m.strip()]
    cases = _load_cases(args.n)
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    sem = asyncio.Semaphore(args.concurrency)

    async def _guarded(c):
        async with sem:
            return await _judge_case(client, c, candidates, args.judge)

    print(f"# 후보 {candidates} | 심판 {args.judge} | 케이스 {len(cases)}건\n")
    results = [r for r in await asyncio.gather(*[_guarded(c) for c in cases]) if r]

    wins = defaultdict(int)
    rank_sum = defaultdict(float)
    for r in results:
        for pos, model in enumerate(r["ranking"]):
            rank_sum[model] += pos + 1
        wins[r["ranking"][0]] += 1

    n_judged = len(results)
    print(f"심판 완료: {n_judged}/{len(cases)} 케이스\n")
    print("model | 1위(승) | 승률 | 평균순위(↓좋음)")
    print("-|-|-|-")
    for m in candidates:
        wr = wins[m] / n_judged if n_judged else 0
        ar = rank_sum[m] / n_judged if n_judged else 0
        print(f"{m} | {wins[m]} | {wr:.0%} | {ar:.2f}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n→ {args.out} (케이스별 랭킹·근거)")


if __name__ == "__main__":
    asyncio.run(main())
