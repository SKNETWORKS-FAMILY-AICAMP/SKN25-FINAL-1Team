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
from app.utils.followup_policy import is_followup_limited

from .contracts import Flow, Phase, SessionContext


def _enum_value(x) -> str:
    return x.value if hasattr(x, "value") else x


async def _compute_phase(db, session) -> Phase:
    """예약 상태로 국면 판정 (기존 chat.py 로직과 동일 기준)."""
    if session.emrid is None:
        return Phase.PRE_BOOKING
    # deleted_at 필터 — chat.py/followup.py와 동일 기준(soft-delete된 예약은 무시).
    sched = (await db.execute(
        select(Schedule).where(
            Schedule.emrid == session.emrid,
            Schedule.deleted_at.is_(None),
        )
    )).scalars().first()
    if not sched or not sched.confirmed_time or sched.status == "CANCELLED":
        return Phase.PRE_BOOKING
    confirmed = sched.confirmed_time
    if confirmed.tzinfo is None:
        confirmed = confirmed.replace(tzinfo=timezone.utc)
    return Phase.BOOKED


async def _current_schedule(db, emrid: int | None):
    if emrid is None:
        return None
    return (await db.execute(
        select(Schedule).where(
            Schedule.emrid == emrid,
            Schedule.deleted_at.is_(None),
        )
    )).scalars().first()


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
    sched = await _current_schedule(db, session.emrid)
    followup_limited = False
    if sched and sched.confirmed_time and sched.status != "CANCELLED":
        confirmed = sched.confirmed_time
        if confirmed.tzinfo is None:
            confirmed = confirmed.replace(tzinfo=timezone.utc)
        followup_limited = is_followup_limited(confirmed, now=datetime.now(timezone.utc))

    # 예약 후(BOOKED) 챗에서 '문진 작성 후 새로 예약하기'를 고른 세션 — 같은 세션에서 새 문진을
    # 돌릴 수 있게 phase를 PRE_BOOKING으로 강등한다(문진 완료 시 triage가 새 emrid 발급 + 플래그 해제).
    new_booking = bool(orch.get("new_booking"))
    if new_booking and phase == Phase.BOOKED:
        phase = Phase.PRE_BOOKING

    active_flow = orch.get("active_flow") or "idle"
    if phase == Phase.BOOKED:
        active_flow = "idle"

    return SessionContext(
        session_id=session.id,
        userid=session.userid,
        petid=session.petid,
        pet_info=await _pet_info(db, session.petid),
        hospitalid=await _primary_hospitalid(db, session.userid),
        emrid=session.emrid,
        # 현재 예약(soft-delete 제외) — 모니터링/이벤트가 'BOOKED일 때 어떤 예약인지'를 알 수 있게 채운다.
        scheduleid=(sched.scheduleid if sched else None),
        user_message=user_message,
        attachments=attachments or [],
        history=session.messages or [],
        phase=phase,
        active_flow=Flow(active_flow),
        reception_streak=int(orch.get("reception_streak", 0) or 0),
        triage_state=orch.get("triage_state") or {},
        followup_summary=orch.get("followup_summary") or "",
        last_followup_reply_kind=orch.get("last_followup_reply_kind") or "",
        asked_followup_fields=orch.get("asked_followup_fields") or [],
        pending_confirmation_action=orch.get("pending_confirmation_action") or "",
        last_media_summary=orch.get("last_media_summary") or "",
        followup_limited=followup_limited,
        new_booking=new_booking,
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
    existing = dict(session.orch_state or {})
    preserved = {
        k: v
        for k, v in existing.items()
        if k.startswith("followup_limit_notice_")
    }
    session.orch_state = {
        **preserved,
        "active_flow": _enum_value(ctx.active_flow),
        "reception_streak": ctx.reception_streak,
        "triage_state": ctx.triage_state,
        "followup_summary": ctx.followup_summary,
        "last_followup_reply_kind": ctx.last_followup_reply_kind,
        "asked_followup_fields": ctx.asked_followup_fields,
        "pending_confirmation_action": ctx.pending_confirmation_action,
        "last_media_summary": ctx.last_media_summary,
        "new_booking": bool(ctx.new_booking),
    }
    flag_modified(session, "orch_state")
    db.add(session)
    await db.commit()
