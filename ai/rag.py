"""공용 RAG — triage_rag_documents(pgvector)에서 유사 상담사례 검색."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.triage_rag_document import TriageRagDocument
from ai.llm import call_llm_json

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
RAG_USABLE_THRESHOLD = 0.60  # 유사도 ≥ 이 값이면 '관련 사례'로 사용

_EXPAND_PROMPT = (
    "너는 수의 트리아지 RAG 검색용 '쿼리 확장기'야. 보호자의 짧은 한국어 증상 표현을 "
    "유사 상담사례 검색이 잘 되도록 동의어·구어/표준어·관련 임상용어로 확장해. "
    "원문 의미를 벗어나지 말고(없는 증상 추가 금지), 진단 단정 금지, 특정 질환으로 좁히지 마.\n"
    'JSON으로만 반환: {{"expansion": "확장 키워드를 공백으로 나열"}}\n\n'
    "원문: {query}"
)


# 검색 쿼리 LLM 확장 (실패 시 원문 그대로 — fail-open)
async def expand_query_llm(query: str) -> str:
    query = " ".join((query or "").split())
    if not query:
        return query
    try:
        data = await call_llm_json(_EXPAND_PROMPT.format(query=query))
        expansion = " ".join(str((data or {}).get("expansion") or "").split())
        return f"{query}\n{expansion}" if expansion else query
    except Exception as exc:
        logger.warning("[RAG] query expansion skipped: %s", exc)
        return query


# 검색 결과 1건
@dataclass(slots=True)
class TriageRagMatch:
    source_file: str
    department: str
    disease: str | None
    life_cycle: str | None
    input_text: str
    output_text: str
    distance: float

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "department": self.department,
            "disease": self.disease,
            "life_cycle": self.life_cycle,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "distance": self.distance,
            "similarity": self.similarity,
        }


# 쿼리 임베딩 (OpenAI — 동기 호출이라 스레드로 분리)
def _embed_query_sync(query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for RAG search")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(model=model, input=query, dimensions=EMBEDDING_DIMENSIONS)
    return response.data[0].embedding


async def embed_query(query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")
    return await asyncio.to_thread(_embed_query_sync, query, model)


# 유사 상담사례 검색 (pgvector 코사인 거리, 가까운 순)
async def search_similar_triage_cases(
    db: AsyncSession,
    query: str,
    *,
    top_k: int = 5,
    department: str | None = None,
    expand_query: bool = True,
    model: str = EMBEDDING_MODEL,
) -> list[TriageRagMatch]:
    search_query = await expand_query_llm(query) if expand_query else query
    query_embedding = await embed_query(search_query, model=model)
    distance = TriageRagDocument.embedding.cosine_distance(query_embedding).label("distance")

    stmt = select(TriageRagDocument, distance)
    if department:
        stmt = stmt.where(TriageRagDocument.department == department.strip())
    stmt = stmt.order_by(distance).limit(top_k)

    result = await db.execute(stmt)
    matches: list[TriageRagMatch] = []
    for document, distance_value in result.all():
        matches.append(TriageRagMatch(
            source_file=document.source_file,
            department=document.department,
            disease=document.disease,
            life_cycle=document.life_cycle,
            input_text=document.input_text,
            output_text=document.output_text,
            distance=float(distance_value),
        ))
    return matches
