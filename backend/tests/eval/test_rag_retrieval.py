"""[정량 평가 6 · LIVE] RAG 검색 품질 — Hit@k / Precision@k / MRR (LLM-free 채점).

RAG(유사 상담사례 벡터검색)가 '같은 증상을 다룬' 사례를 잘 끌어오는지 측정한다.

[관련성 정의 — 도메인 적합]
  소형 동물병원은 진료과가 나뉘지 않으므로(수의사 1인 전진료), 관련성을 '진료과'가 아니라
  '증상 주제 일치'로 본다: 검색된 사례의 보호자 질문 본문(input_text)에 그 질문의
  증상어(rag_golden.symptom_terms)가 등장하면 on-topic(관련 있음).

[신뢰 설계]
  · 정답(어떤 증상어가 관련인가)은 사람이 라벨(rag_golden.GOLDEN) — 검수 가능.
  · 채점은 문자열 매칭(결정론) — LLM이 관련성을 점수 매기지 않는다.
  · 지표:
      Hit@k       = top-k 안에 on-topic 사례가 1개라도 있으면 hit. hit/전체.
      Precision@k = top-k 중 on-topic 비율의 평균(검색 결과가 얼마나 깨끗한가).
      MRR         = 첫 on-topic 사례 순위의 역수 평균(1/rank).

임베딩 호출이 있으므로 RUN_LIVE_EVAL=1 + 코퍼스 적재(load_triage_rag.py) 필요.
산출물: backend/eval_rag_retrieval.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    class _PytestShim:
        class mark:
            @staticmethod
            def skipif(*a, **k):
                def deco(fn):
                    return fn
                return deco
    pytest = _PytestShim()  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from tests.eval.rag_golden import GOLDEN  # noqa: E402

_OUT = Path(__file__).resolve().parents[2] / "eval_rag_retrieval.json"
_TOP_K = int(os.environ.get("EVAL_RAG_TOPK", "5"))


def _on_topic(match, terms: list[str]) -> bool:
    """검색된 사례가 같은 증상을 다루는가 — 질문/답변 본문에 증상어 등장 여부(결정론)."""
    body = f"{match.input_text or ''} {match.output_text or ''}"
    return any(t in body for t in terms)


async def _run() -> dict:
    from app.db.session import AsyncSessionLocal
    from ai.triage.rag import search_similar_triage_cases

    rows = []
    hits = 0
    rr_sum = 0.0
    prec_sum = 0.0
    for case in GOLDEN:
        terms = case["symptom_terms"]
        async with AsyncSessionLocal() as db:
            matches = await search_similar_triage_cases(
                db, case["query"], top_k=_TOP_K, expand_query=False
            )
        flags = [_on_topic(m, terms) for m in matches]
        on_topic_n = sum(flags)
        first_rank = next((i for i, f in enumerate(flags, 1) if f), 0)
        hit = first_rank > 0
        hits += int(hit)
        rr_sum += (1.0 / first_rank) if first_rank else 0.0
        prec_sum += (on_topic_n / len(flags)) if flags else 0.0
        rows.append({
            "query": case["query"], "symptom_terms": terms,
            "retrieved": len(matches), "on_topic": on_topic_n,
            "first_hit_rank": first_rank, "hit": hit,
            "top_similarity": round(matches[0].similarity, 4) if matches else None,
            # 검수용: 1순위 사례 본문 일부(정말 같은 증상인지 눈으로 확인)
            "top1_input_excerpt": (matches[0].input_text[:80] + "…") if matches else None,
        })

    n = len(GOLDEN)
    return {
        "top_k": _TOP_K, "n_queries": n,
        "hit_at_k": round(hits / n, 4) if n else 0.0,
        "precision_at_k": round(prec_sum / n, 4) if n else 0.0,
        "mrr": round(rr_sum / n, 4) if n else 0.0,
        "rows": rows,
    }


@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVAL") != "1",
                    reason="LIVE 평가: RUN_LIVE_EVAL=1 + RAG 코퍼스 적재 필요")
def test_rag_retrieval_measured():
    report = asyncio.run(_run())
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert report["n_queries"] > 0
    assert any(r["retrieved"] for r in report["rows"]), "검색 결과 0 — 코퍼스 적재 확인"


if __name__ == "__main__":
    rep = asyncio.run(_run())
    _OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[RAG 검색] {rep['n_queries']}쿼리 @top{rep['top_k']} → "
          f"Hit@{rep['top_k']} {rep['hit_at_k']*100:.1f}%, "
          f"Precision@{rep['top_k']} {rep['precision_at_k']*100:.1f}%, MRR {rep['mrr']:.3f}")
    print(f"→ {_OUT}")
