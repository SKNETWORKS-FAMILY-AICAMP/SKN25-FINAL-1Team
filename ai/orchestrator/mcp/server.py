"""medipaw-mcp — 병원 안내 read-only MCP 서버 (FastMCP / Streamable HTTP). 설계서 §9.1.

응대(reception) 에이전트가 'LLM tool-calling'으로 호출하는 stateless 조회 도구만 노출한다.
기존 모델/CRUD를 얇게 감싼 래퍼이며 프로덕션 파이프라인을 건드리지 않는다.

실행(별도 docker 서비스):  python -m ai.orchestrator.mcp.server   (streamable-http, 0.0.0.0:8765)
필요 환경: backend/.env 의 DATABASE_URL, OPENAI_API_KEY (앱과 동일).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# app.*(backend) 와 ai.*(repo root) 를 모두 import 하므로 둘 다 path 에 넣고,
# settings 의 env_file=".env"(cwd 상대경로)가 로드되도록 cwd 를 backend 로 고정한다.
_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_REPO_ROOT))
if _BACKEND_DIR.exists():
    os.chdir(_BACKEND_DIR)

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402

mcp = FastMCP(
    "medipaw-mcp",
    instructions=(
        "MediPaw 동물병원 안내 도구. 병원 정보·운영시간·다음 진료일·빈 예약 슬롯을 조회한다. "
        "보호자의 병원 관련 질문에 답하기 위해 필요한 도구를 골라 호출하라. read-only."
    ),
    # 내부 docker 네트워크 전용 서비스 — Host 헤더가 'medipaw-mcp:8765'라 기본 DNS 리바인딩
    # 보호(localhost만 허용)에 막혀 421이 난다. 내부 전용이므로 보호를 끈다.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


def _fmt_t(t) -> str:
    return str(t)[:5] if t else ""


@mcp.tool(
    name="get_hospital_info",
    description="병원 이름·주소·전화·소개·특징을 조회한다. (병원 위치/연락처/소개 질문)",
)
async def get_hospital_info(hospitalid: int) -> dict:
    """병원 기본 정보 + 프로필(소개/특징)."""
    from app.models.hospital import Hospital
    from app.models.hospital_profile import HospitalProfile
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        hos = (await db.execute(select(Hospital).where(Hospital.hospitalid == hospitalid))).scalar_one_or_none()
        if not hos:
            return {"found": False}
        prof = (await db.execute(
            select(HospitalProfile).where(HospitalProfile.hospitalid == hospitalid)
        )).scalar_one_or_none()
        return {
            "found": True,
            "name": hos.hospital_name,
            "address": hos.hospital_address,
            "phone": hos.hospital_number,
            "tagline": getattr(prof, "tagline", None) if prof else None,
            "features": getattr(prof, "features", None) if prof else None,
            "intro": getattr(prof, "intro", None) if prof else None,
        }


@mcp.tool(
    name="get_operating_hours",
    description="병원의 요일별 운영시간·점심시간과 향후 30일 임시 휴진일을 조회한다. (영업시간/휴진 질문)",
)
async def get_operating_hours(hospitalid: int) -> dict:
    """요일별 운영시간 + 임박한 휴진일."""
    from app.models.vet_schedule import HospitalClosedDate, HospitalWeeklySchedule
    from sqlalchemy import and_, select

    async with AsyncSessionLocal() as db:
        weekly = (await db.execute(
            select(HospitalWeeklySchedule).where(HospitalWeeklySchedule.hospitalid == hospitalid)
        )).scalars().all()
        hours = []
        for wk in sorted(weekly, key=lambda x: x.day_of_week):
            hours.append({
                "day": _DAY_NAMES[wk.day_of_week],
                "is_open": bool(wk.is_open),
                "start": _fmt_t(wk.start_time),
                "end": _fmt_t(wk.end_time),
                "lunch_start": _fmt_t(wk.lunch_start),
                "lunch_end": _fmt_t(wk.lunch_end),
            })
        closed = (await db.execute(
            select(HospitalClosedDate).where(and_(
                HospitalClosedDate.hospitalid == hospitalid,
                HospitalClosedDate.date >= date.today(),
                HospitalClosedDate.date <= date.today() + timedelta(days=30),
            ))
        )).scalars().all()
        return {
            "hours": hours,
            "upcoming_closed_dates": [str(c.date) for c in closed],
        }


@mcp.tool(
    name="get_next_open_day",
    description="오늘 이후 병원이 다음으로 진료하는 날짜를 찾는다. (오늘 휴진/다음 진료일 질문)",
)
async def get_next_open_day(hospitalid: int, max_scan_days: int = 30) -> dict:
    """주간 스케줄 + 휴진일 + 법정공휴일을 고려한 다음 진료일."""
    from app.crud.schedule import _is_legal_holiday
    from app.models.vet_schedule import HospitalClosedDate, HospitalWeeklySchedule
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        weekly = {
            wk.day_of_week: wk for wk in (await db.execute(
                select(HospitalWeeklySchedule).where(HospitalWeeklySchedule.hospitalid == hospitalid)
            )).scalars().all()
        }
        closed = {
            c.date for c in (await db.execute(
                select(HospitalClosedDate).where(HospitalClosedDate.hospitalid == hospitalid)
            )).scalars().all()
        }
        today = date.today()
        for i in range(max_scan_days + 1):
            d = today + timedelta(days=i)
            wk = weekly.get(d.weekday())
            open_today = (wk.is_open if wk is not None else d.weekday() < 5)
            if open_today and d not in closed and not _is_legal_holiday(d):
                wk_row = weekly.get(d.weekday())
                return {
                    "date": d.isoformat(),
                    "day": _DAY_NAMES[d.weekday()],
                    "is_today": i == 0,
                    "start": _fmt_t(wk_row.start_time) if wk_row else "09:00",
                    "end": _fmt_t(wk_row.end_time) if wk_row else "18:00",
                }
        return {"date": None}


@mcp.tool(
    name="find_open_slots",
    description=(
        "응급도(urgency_level_num 1~5)에 따라 가장 빠른 빈 예약 슬롯을 찾는다. "
        "read-only — 실제 예약 확정은 하지 않는다. 결과는 가장 이른 순."
    ),
)
async def find_open_slots(
    urgency_level_num: int,
    duration_min: int = 30,
    limit: int = 3,
    doctorid: int | None = None,
) -> dict:
    """응급도 기반 가장 빠른 빈 슬롯 조회."""
    from app.crud.schedule import find_earliest_slots

    async with AsyncSessionLocal() as db:
        slots = await find_earliest_slots(
            db,
            urgency_level_num=urgency_level_num,
            duration_min=duration_min,
            limit=limit,
            doctorid=doctorid,
        )
    return {"count": len(slots), "slots": slots}


if __name__ == "__main__":
    # Streamable HTTP — 별도 docker 서비스로 노출 (기본 0.0.0.0:8000/mcp).
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.getenv("MCP_PORT", "8765"))
    mcp.run(transport="streamable-http")
