"""세션 상태 로드/저장 — DB(chat_historyDB.orch_state) ↔ SessionContext. 담당: 리드.
AGENT_SPECS '공통 동작 규칙 A/B'.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.models.guardian_hospital import GuardianHospital
from app.models.pet import Pet
from app.models.schedule import Schedule

from .contracts import Flow, Phase, SessionContext


def _enum_value(x) -> str:
    return x.value if hasattr(x, "value") else x


async def _compute_phase(db, session) -> Phase:
    """예약 상태로 국면 판정 (기존 chat.py 로직과 동일 기준)."""
    if session.emrid is None:
        return Phase.PRE_BOOKING
    sched = (await db.execute(
        select(Schedule).where(Schedule.emrid == session.emrid)
    )).scalars().first()
    if not sched or not sched.confirmed_time or sched.status == "CANCELLED":
        return Phase.PRE_BOOKING
    confirmed = sched.confirmed_time
    if confirmed.tzinfo is None:
        confirmed = confirmed.replace(tzinfo=timezone.utc)
    return Phase.BOOKED if datetime.now(timezone.utc) <= confirmed else Phase.CLOSED


async def _pet_info(db, petid: int) -> dict:
    pet = (await db.execute(select(Pet).where(Pet.petid == petid))).scalar_one_or_none()
    if not pet:
        return {}
    return {
        "name": pet.petname, "species": pet.species, "breed": pet.breed,
        "gender": pet.gender, "weight": float(pet.weight_kg) if pet.weight_kg is not None else None,
        "is_neutered": pet.is_neutered,
    }


async def _primary_hospitalid(db, userid: int) -> int | None:
    rows = (await db.execute(
        select(GuardianHospital).where(GuardianHospital.userid == userid)
    )).scalars().all()
    if not rows:
        return None
    primary = next((r for r in rows if r.is_primary), None)
    return (primary or rows[-1]).hospitalid


async def build_context(db, session, user_message: str,
                        attachments: list[str] | None = None) -> SessionContext:
    """DB → SessionContext. session = 이미 로드된 chat_historyDB row."""
    orch = session.orch_state or {}
    phase = await _compute_phase(db, session)

    active_flow = orch.get("active_flow") or "idle"
    if phase in (Phase.BOOKED, Phase.CLOSED):
        active_flow = "idle"

    return SessionContext(
        session_id=session.id,
        userid=session.userid,
        petid=session.petid,
        pet_info=await _pet_info(db, session.petid),
        hospitalid=await _primary_hospitalid(db, session.userid),
        emrid=session.emrid,
        scheduleid=None,
        user_message=user_message,
        attachments=attachments or [],
        history=session.messages or [],
        phase=phase,
        active_flow=Flow(active_flow),
        reception_streak=int(orch.get("reception_streak", 0) or 0),
        triage_state=orch.get("triage_state") or {},
        followup_summary=orch.get("followup_summary") or "",
        db=db,
        session=session,
    )


def apply_patch(ctx: SessionContext, patch: dict) -> None:
    """AgentResult.state_patch를 ctx에 머지. 키 소유권은 AGENT_SPECS B 표 준수."""
    for key, value in (patch or {}).items():
        if hasattr(ctx, key):
            setattr(ctx, key, value)


async def save_state(db, ctx: SessionContext) -> None:
    """ctx 상태를 chat_historyDB.orch_state(JSON)에 저장. (phase는 매번 계산하므로 저장 안 함)"""
    session = ctx.session
    session.orch_state = {
        "active_flow": _enum_value(ctx.active_flow),
        "reception_streak": ctx.reception_streak,
        "triage_state": ctx.triage_state,
        "followup_summary": ctx.followup_summary,
    }
    flag_modified(session, "orch_state")
    db.add(session)
    await db.commit()
