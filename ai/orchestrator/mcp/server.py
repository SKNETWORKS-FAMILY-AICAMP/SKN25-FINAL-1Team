"""medipaw-mcp — 진짜 MCP 서버 (FastMCP). 담당: 리드(도구 스펙 A와 합의). 설계서 §9.1 / AGENT_SPECS §1.

stateless 조회 도구만 노출. docker-compose 별도 서비스 + Streamable HTTP 전송.
지금은 import 에러 안 나게 주석 골격만 — `pip install mcp` 후 주석 해제.
"""
from __future__ import annotations

# TODO(리드): MCP 서버 구현
# from mcp.server.fastmcp import FastMCP
#
# mcp = FastMCP("medipaw-mcp")
#
# @mcp.tool()
# async def get_hospital_info(hospitalid: int) -> dict:
#     """병원 이름·주소·전화·소개·특징. (hospitalDB + hospital_profileDB)"""
#     ...
#
# @mcp.tool()
# async def get_operating_hours(hospitalid: int, date: str | None = None) -> dict:
#     """요일별 운영·점심·오늘 진료 여부. (vet_scheduleDB + hospital_closed_datesDB)"""
#     ...
#
# @mcp.tool()
# async def get_next_open_day(hospitalid: int) -> dict:
#     """다음 진료일. (vet_scheduleDB + closed_dates fill-forward)"""
#     ...
#
# @mcp.tool()
# async def get_pet_history(petid: int) -> dict:
#     """과거 방문·진단·처방 요약. (build_patient_context 재활용)"""
#     ...
#
# @mcp.tool()
# async def recommend_slots(emrid: int, urgency: str, duration_min: int) -> dict:
#     """추천 예약 슬롯. (crud/schedule.recommend_slots, 결정론)"""
#     ...
#
# if __name__ == "__main__":
#     mcp.run(transport="streamable-http")
