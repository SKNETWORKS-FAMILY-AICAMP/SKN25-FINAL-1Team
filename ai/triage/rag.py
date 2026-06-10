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

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# 유사도가 이 값 이상이면 '관련 사례(usable)'로 본다. chart 주입 필터 + RAG 품질 판정에 공용.
RAG_USABLE_THRESHOLD = 0.60

_EXPAND_SYSTEM = (
    "너는 수의 트리아지 RAG 검색용 '쿼리 확장기'야. 보호자의 짧은 한국어 증상 표현을, "
    "유사 상담사례 검색이 잘 되도록 동의어·구어/표준어 변환·관련 임상용어로 확장해. "
    "원문의 의미 범위를 벗어나지 말고(없는 증상 추가 금지), 진단을 단정하지 마. "
    "특정 질환·진료과로 억지로 좁히지 말고 표현만 풍부하게 만들어.\n"
    'JSON으로만 반환: {"expansion": "확장 키워드를 공백으로 나열"}'
)


async def expand_query_llm(query: str) -> str:
    """LLM으로 검색 쿼리를 확장한다(하드코딩 키워드 대체).

    어떤 증상이든 일반적으로 동작하며, 실패하면 원문을 그대로 반환(fail-open)한다.
    """
    query = " ".join((query or "").split())
    if not query:
        return query
    try:
        from ai.agents.base import call_openai

        result = await call_openai(
            [{"role": "user", "content": query}],
            _EXPAND_SYSTEM,
            # gpt-5 계열(추론 모델)은 reasoning_tokens가 예산을 먼저 소모하므로
            # 120은 JSON을 완성하기 전에 한도 초과로 실패한다. 여유를 둔다.
            max_tokens=512,
            agent="triage_rag_expand",
        )
        expansion = ""
        if isinstance(result, dict):
            expansion = " ".join(str(result.get("expansion") or "").split())
        return f"{query}\n{expansion}" if expansion else query
    except Exception as exc:
        logger.warning("[TriageRAG] LLM query expansion skipped: %s", exc)
        return query


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


def _embed_query_sync(query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for triage RAG search")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(
        model=model,
        input=query,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


async def embed_query(query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")
    return await asyncio.to_thread(_embed_query_sync, query, model)


async def search_similar_triage_cases(
    db: AsyncSession,
    query: str,
    *,
    top_k: int = 5,
    department: str | None = None,
    expand_query: bool = True,
    model: str = EMBEDDING_MODEL,
) -> list[TriageRagMatch]:
    # 진료과는 더 이상 키워드로 자동 추론하지 않는다(하드코딩 제거).
    # 관련도는 벡터 유사도가 결정하고, department는 호출부가 명시할 때만 필터로 쓴다.
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
        matches.append(
            TriageRagMatch(
                source_file=document.source_file,
                department=document.department,
                disease=document.disease,
                life_cycle=document.life_cycle,
                input_text=document.input_text,
                output_text=document.output_text,
                distance=float(distance_value),
            )
        )
    return matches
