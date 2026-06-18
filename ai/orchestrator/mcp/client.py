"""MCP 클라이언트 — 지휘자가 medipaw-mcp에 연결해 도구를 LangChain 툴로 로드. 담당: 리드. 설계서 §9.1.

langchain-mcp-adapters 사용. 응대/스케줄 노드가 이 툴들을 tool-calling으로 호출.
"""
from __future__ import annotations

# TODO(리드): MCP 클라이언트 연결
# from langchain_mcp_adapters.client import MultiServerMCPClient
#
# _client = MultiServerMCPClient({
#     "medipaw": {"url": "http://medipaw-mcp:8765/mcp", "transport": "streamable_http"},
# })


async def get_mcp_tools():
    """MCP 서버에 연결 → list_tools → LangChain 툴 리스트 반환.

    Day1 게이트: 이 함수가 빈 서버에 연결해 도구 목록을 받아오면 'MCP 왕복' 성공.
    """
    raise NotImplementedError("MCP 클라이언트 연결 구현 필요 (설계서 §9.1)")
