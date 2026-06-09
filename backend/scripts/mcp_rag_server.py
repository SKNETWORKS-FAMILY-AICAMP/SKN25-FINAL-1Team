"""MediPaw 수의 트리아지 RAG — read-only MCP 서버 (stdio).

Codex 같은 MCP 호스트에서 수의 지식베이스(triage_rag_documents, pgvector)를
대화형으로 검색하기 위한 개발/탐색용 도구다. 기존
``ai.triage.rag.search_similar_triage_cases`` 를 얇게 감싼 read-only 래퍼이며,
프로덕션 파이프라인(schedules.py post-booking 주입)은 건드리지 않는다.

실행: ``python backend/scripts/mcp_rag_server.py`` (stdio transport)
필요 환경: backend/.env 의 DATABASE_URL, OPENAI_API_KEY (앱과 동일 설정 사용).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 이 스크립트는 app.*(backend) 와 ai.*(repo root) 를 모두 import 하므로
# backend 디렉터리(app)와 repo 루트(ai)를 둘 다 path 에 넣는다.
_BACKEND_DIR = Path(__file__).parents[1]
_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_REPO_ROOT))

# settings 의 env_file=".env" 가 cwd 기준 상대경로라, MCP 호스트가 어느 위치에서
# 띄우든 backend/.env(OPENAI_API_KEY·DATABASE_URL) 가 로드되도록 cwd 를 고정한다.
# 반드시 app.core.config 를 끌어오는 import 보다 먼저 실행돼야 한다.
os.chdir(_BACKEND_DIR)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from ai.triage.rag import (  # noqa: E402
    expand_query_llm,
    search_similar_triage_cases,
)

mcp = FastMCP(
    "medipaw-vet-rag",
    instructions=(
        "MediPaw 수의 트리아지 지식베이스(유사 상담사례) 검색 도구. "
        "보호자 증상 표현이나 임상 질문으로 유사 사례를 벡터 검색한다. "
        "참고용 검색 결과일 뿐 진단 확정 근거가 아니다."
    ),
)


def _clip(text: str | None, max_chars: int) -> str:
    text = " ".join((text or "").split())
    if max_chars > 0 and len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


@mcp.tool(
    name="search_triage_cases",
    description=(
        "수의 트리아지 RAG에서 유사 상담사례를 벡터 검색한다. "
        "query 는 보호자 증상 표현이나 임상 질문(한국어). "
        "department(예: 내과/외과/안과) 를 주면 해당 진료과로 필터링한다. "
        "결과는 유사도 내림차순. 참고용이며 진단 확정 근거가 아니다."
    ),
)
async def search_triage_cases(
    query: str,
    top_k: int = 5,
    department: str | None = None,
    expand_query: bool = True,
    max_chars: int = 600,
) -> dict:
    """유사 트리아지 사례 검색.

    Args:
        query: 검색할 증상/질문 텍스트.
        top_k: 반환할 사례 수 (기본 5).
        department: 진료과 필터 (선택). None 이면 전체에서 유사도로만 검색.
        expand_query: LLM 쿼리 확장 사용 여부 (기본 True).
        max_chars: 각 사례 본문 표시 길이 제한 (0=무제한).
    """
    expanded = query if not expand_query else await expand_query_llm(query)
    async with AsyncSessionLocal() as db:
        matches = await search_similar_triage_cases(
            db,
            query,
            top_k=top_k,
            department=department,
            expand_query=expand_query,
        )

    return {
        "query": query,
        "expanded_query": _clip(expanded, 0) if expanded != query else None,
        "department_filter": department,
        "count": len(matches),
        "results": [
            {
                "rank": idx,
                "similarity": round(m.similarity, 4),
                "department": m.department,
                "disease": m.disease,
                "life_cycle": m.life_cycle,
                "source_file": m.source_file,
                "matched_input": _clip(m.input_text, max_chars),
                "answer_output": _clip(m.output_text, max_chars),
            }
            for idx, m in enumerate(matches, start=1)
        ],
    }


@mcp.tool(
    name="preview_expanded_query",
    description=(
        "검색 전 LLM 쿼리 확장 결과만 미리 본다(디버깅용). "
        "실제 검색은 하지 않고, 원문이 어떤 키워드로 확장되는지 확인한다."
    ),
)
async def preview_expanded_query(query: str) -> dict:
    """LLM 쿼리 확장 미리보기(검색 없음)."""
    expanded = await expand_query_llm(query)
    return {"query": query, "expanded_query": expanded, "changed": expanded != query}


@mcp.tool(
    name="find_open_slots",
    description=(
        "응급도(urgency_level_num 1~5)에 따라 '가장 빠른' 빈 진료 슬롯을 찾는다. "
        "급할수록(응급=1) 더 이른 날부터 스캔해 빠른 시간을 우선 추천한다. "
        "read-only 조회만 — 실제 예약 확정은 하지 않는다(사람이 슬롯을 골라 확정). "
        "결과 슬롯은 날짜·시간 오름차순(가장 이른 순)."
    ),
)
async def find_open_slots(
    urgency_level_num: int,
    duration_min: int = 30,
    limit: int = 3,
    doctorid: int | None = None,
) -> dict:
    """응급도 기반 가장 빠른 빈 슬롯 조회(예약 오케스트레이션 에이전트용).

    Args:
        urgency_level_num: 트리아지 응급도 1~5 (1=응급 → 오늘부터, 4~5=일반 → 뒤로).
        duration_min: 진료 소요시간(분). 연속 슬롯 계산 기준.
        limit: 추천할 슬롯 수 (기본 3).
        doctorid: 특정 의사 지정(선택). None이면 기본 의사.
    """
    from app.crud.schedule import find_earliest_slots

    async with AsyncSessionLocal() as db:
        slots = await find_earliest_slots(
            db,
            urgency_level_num=urgency_level_num,
            duration_min=duration_min,
            limit=limit,
            doctorid=doctorid,
        )
    return {
        "urgency_level_num": urgency_level_num,
        "duration_min": duration_min,
        "count": len(slots),
        "slots": slots,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
