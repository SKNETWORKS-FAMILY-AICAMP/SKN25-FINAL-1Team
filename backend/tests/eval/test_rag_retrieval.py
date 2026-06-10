"""[정량 평가 6 · LIVE] RAG 검색 품질 — Recall@k & MRR (LLM-free 채점).

RAG(유사 상담사례 벡터검색)가 '관련 있는' 사례를 잘 끌어오는지 측정한다.

신뢰 설계(‘AI가 AI 평가’ 회피):
  · 정답(relevance)은 **사람이 라벨**한다 — rag_golden.GOLDEN 의 expected_department.
    "이 증상 표현은 어느 진료과인가"는 도메인 전문가가 검수 가능한 객관 라벨이다.
  · 채점은 **진료과 문자열 매칭**(결정론) — LLM이 관련성을 점수 매기지 않는다.
  · 측정 지표:
      Recall@k = 기대 진료과 문서가 top-k 안에 1개라도 있으면 hit. hit/전체.
      MRR      = 기대 진료과가 처음 등장한 순위의 역수 평균(1/rank).

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


async def _run() -> dict:
    from app.db.session import AsyncSessionLocal
    from ai.triage.rag import search_similar_triage_cases

    rows = []
    hits = 0
    rr_sum = 0.0
    for case in GOLDEN:
        expected = case["expected_department"]
        async with AsyncSessionLocal() as db:
            matches = await search_similar_triage_cases(
                db, case["query"], top_k=_TOP_K, expand_query=False
            )
        depts = [m.department for m in matches]
        # 기대 진료과가 처음 등장한 순위(1-based). 없으면 0.
        first_rank = next((i for i, d in enumerate(depts, 1) if d == expected), 0)
        hit = first_rank > 0
        hits += int(hit)
        rr_sum += (1.0 / first_rank) if first_rank else 0.0
        rows.append({
            "query": case["query"], "expected_department": expected,
            "retrieved_departments": depts, "first_hit_rank": first_rank, "hit": hit,
            "top_similarity": round(matches[0].similarity, 4) if matches else None,
        })

    n = len(GOLDEN)
    return {
        "top_k": _TOP_K, "n_queries": n,
        "recall_at_k": round(hits / n, 4) if n else 0.0,
        "mrr": round(rr_sum / n, 4) if n else 0.0,
        "rows": rows,
    }


@pytest.mark.skipif(os.environ.get("RUN_LIVE_EVAL") != "1",
                    reason="LIVE 평가: RUN_LIVE_EVAL=1 + RAG 코퍼스 적재 필요")
def test_rag_retrieval_measured():
    report = asyncio.run(_run())
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert report["n_queries"] > 0
    # 코퍼스가 적재돼 있으면 최소한 일부는 검색돼야 한다(완전 0이면 미적재 의심).
    assert any(r["retrieved_departments"] for r in report["rows"]), "검색 결과 0 — 코퍼스 적재 확인"


if __name__ == "__main__":
    rep = asyncio.run(_run())
    _OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[RAG 검색] {rep['n_queries']}쿼리 @top{rep['top_k']} → "
          f"Recall@{rep['top_k']} {rep['recall_at_k']*100:.1f}%, MRR {rep['mrr']:.3f}")
    print(f"→ {_OUT}")
