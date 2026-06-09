"""백엔드 → MediPaw MCP 서버(stdio) 클라이언트.

예약 오케스트레이션 에이전트가 MCP 툴(find_open_slots, search_triage_cases)을
'MCP 프로토콜로' 호출하기 위한 얇은 클라이언트다. 백엔드가 직접 함수를 부르지 않고
MCP 서버를 통하게 하여, 이 프로젝트의 'MCP 기반 자동화' 요건을 실제로 충족한다.

전송: stdio — 백엔드와 동일한 venv 파이썬(sys.executable)으로 mcp_rag_server.py 를
서브프로세스로 띄워 붙는다. (서버가 자체적으로 cwd=backend 로 chdir 하고 .env 를 읽음)

주의: 호출마다 서브프로세스를 새로 띄운다(콜드스타트 비용 있음). 데모/저빈도 호출엔
충분하며, 고빈도/프로덕션은 영속 세션 또는 HTTP 전송으로 전환을 고려한다.
"""
from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# repo_root/backend/scripts/mcp_rag_server.py
_SERVER_SCRIPT = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "mcp_rag_server.py"


def _server_params() -> StdioServerParameters:
    # 백엔드를 실행 중인 venv 파이썬을 그대로 써서 mcp/app 의존성을 보장한다.
    return StdioServerParameters(command=sys.executable, args=[str(_SERVER_SCRIPT)])


@asynccontextmanager
async def mcp_session():
    """초기화까지 끝낸 MCP ClientSession 컨텍스트."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _parse_tool_result(result: Any) -> Any:
    """MCP CallToolResult → 파이썬 값. 툴이 dict를 반환하면 JSON 텍스트로 오므로 파싱."""
    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text
    return None


async def list_tool_schemas() -> list[dict]:
    """서버의 툴들을 OpenAI function-calling 스키마로 변환해 반환한다."""
    async with mcp_session() as session:
        tools = (await session.list_tools()).tools
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


async def call_tool(name: str, arguments: dict | None = None) -> Any:
    """MCP 툴 1회 호출(서브프로세스 spawn → 호출 → 정리). 실패 시 예외 전파."""
    async with mcp_session() as session:
        result = await session.call_tool(name, arguments or {})
    return _parse_tool_result(result)
