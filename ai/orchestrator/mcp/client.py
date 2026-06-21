"""MCP 클라이언트 — medipaw-mcp에 연결해 도구를 LangChain 툴로 로드. 설계서 §9.1.

langchain-mcp-adapters 사용. 응대(reception) 노드가 이 툴들을 tool-calling으로 호출한다.
★ fail-open: MCP 서버가 죽거나 연결 실패하면 [] 반환 → 응대가 기존 방식으로 폴백.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 별도 docker 서비스(medipaw-mcp) Streamable HTTP 엔드포인트.
_MCP_URL = os.getenv("MEDIPAW_MCP_URL", "http://medipaw-mcp:8765/mcp")

_client = None
_tools_cache = None


async def get_mcp_tools(use_cache: bool = True):
    """MCP 서버에 연결 → 도구 목록을 LangChain 툴 리스트로 반환. 실패 시 [].

    Day1 게이트: 이 함수가 서버에 연결해 도구 목록을 받아오면 'MCP 왕복' 성공.
    """
    global _client, _tools_cache
    if use_cache and _tools_cache is not None:
        return _tools_cache
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        if _client is None:
            _client = MultiServerMCPClient({
                "medipaw": {"url": _MCP_URL, "transport": "streamable_http"},
            })
        tools = await _client.get_tools()
        _tools_cache = tools
        logger.info("[mcp] 도구 로드 %s개: %s", len(tools), [t.name for t in tools])
        return tools
    except Exception as e:
        logger.warning("[mcp] 도구 로드 실패(폴백): %s", e)
        return []
