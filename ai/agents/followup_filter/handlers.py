"""경과 필터 보조 핸들러 — 예약/병원/수의사 조회 응답과 pending 액션 실행.

agent.py에서 '동작 변경 없이' 분리한 함수들. DB 조회와 캔드 응답만 담당하고, 어떤
분기로 이 함수가 불릴지는 agent.py가 그대로 결정한다(문구·이벤트·pill 동일).
"""
from __future__ import annotations

from ai.orchestrator.contracts import AgentResult, SessionContext

from .prompts import (
    HOSPITAL_INFO_PILL,
    NEW_BOOKING_DIRECT_PILL,
    NEW_BOOKING_TRIAGE_PILL,
    REBOOK_ACTION_PILL,
    REPLY_NEW_BOOKING_CONFIRM,
    REPLY_PREP_INSTRUCTIONS,
    REPLY_REBOOK,
    REPLY_SCHEDULE_LIST,
    SCHEDULE_LIST_PILL,
)
from .reply_policy import _LIMITED_QUICK_REPLIES, _patch_pending
from app.utils.followup_policy import BOOKING_CHANGE_LIMITED_REPLY


async def appointment_time_reply(ctx: SessionContext) -> str:
    """보호자의 '실제' 예약 시각(confirmed_time)을 안내. 병원 운영시간이 아니라 본인 예약 시각."""
    if ctx.db is None or ctx.emrid is None:
        return "아직 확정된 예약 정보를 찾지 못했어요. 예약을 도와드릴까요?"
    try:
        from sqlalchemy import select

        from app.models.schedule import Schedule
        sched = (await ctx.db.execute(
            select(Schedule).where(Schedule.emrid == ctx.emrid, Schedule.deleted_at.is_(None))
        )).scalars().first()
    except Exception:
        sched = None
    if not sched or not sched.confirmed_time:
        return "아직 확정된 예약이 없어요. 예약을 도와드릴까요?"
    try:
        from app.utils.timezone import to_kst
        k = to_kst(sched.confirmed_time)
        when = f"{k.month}월 {k.day}일 {k.hour:02d}:{k.minute:02d}"
    except Exception:
        when = str(sched.confirmed_time)
    return f"예약 시간은 {when}이에요. 변경을 원하시면 말씀해 주세요."


async def _confirmed_time_text(ctx: SessionContext) -> str:
    """현재 예약 confirmed_time을 'M월 D일 HH:MM'로. 없거나 조회 불가면 ''.

    rebook/cancel 문의에서 '현재 예약'을 한 번 되짚어 맥락 기억을 살리는 데 쓴다(저장·이벤트 없음).
    """
    if ctx.db is None or ctx.emrid is None:
        return ""
    try:
        from sqlalchemy import select

        from app.models.schedule import Schedule
        sched = (await ctx.db.execute(
            select(Schedule).where(Schedule.emrid == ctx.emrid, Schedule.deleted_at.is_(None))
        )).scalars().first()
        if not sched or not sched.confirmed_time:
            return ""
        from app.utils.timezone import to_kst
        k = to_kst(sched.confirmed_time)
        return f"{k.month}월 {k.day}일 {k.hour:02d}:{k.minute:02d}"
    except Exception:
        return ""


async def hospital_info_reply(ctx: SessionContext) -> str:
    """예약된 병원 이름을 우선 안내하고, 있으면 주소/전화까지 짧게 붙인다."""
    if ctx.db is None or ctx.hospitalid is None:
        return "예약된 병원 정보를 바로 확인하지 못했어요. 예약 내역에서 병원 정보를 함께 확인할 수 있어요."
    try:
        from sqlalchemy import select

        from app.models.hospital import Hospital
        hospital = (await ctx.db.execute(
            select(Hospital).where(Hospital.hospitalid == ctx.hospitalid)
        )).scalar_one_or_none()
    except Exception:
        hospital = None
    if not hospital:
        return "예약된 병원 정보를 바로 확인하지 못했어요. 예약 내역에서 병원 정보를 함께 확인할 수 있어요."
    parts = [f"현재 예약된 병원은 {hospital.hospital_name}이에요."]
    if getattr(hospital, "hospital_address", None):
        parts.append(f"주소는 {hospital.hospital_address}입니다.")
    if getattr(hospital, "hospital_number", None):
        parts.append(f"전화번호는 {hospital.hospital_number}입니다.")
    return " ".join(parts[:2])


async def _lookup_vet_name(ctx: SessionContext) -> str:
    """이번 예약(scheduleDB.doctorid → doctorDB.doctor_name)의 담당 수의사 이름. 없으면 ''."""
    if ctx.db is None or ctx.emrid is None:
        return ""
    try:
        from sqlalchemy import select

        from app.models.schedule import Schedule
        sched = (await ctx.db.execute(
            select(Schedule).where(Schedule.emrid == ctx.emrid, Schedule.deleted_at.is_(None))
        )).scalars().first()
        if sched and sched.doctorid is not None:
            from app.models.doctor import Doctor
            doctor = (await ctx.db.execute(
                select(Doctor).where(Doctor.doctorid == sched.doctorid)
            )).scalar_one_or_none()
            return (getattr(doctor, "doctor_name", "") or "").strip()
    except Exception:
        return ""
    return ""


async def vet_info_reply(ctx: SessionContext, *, subjective: bool = False) -> str:
    """담당 수의사 안내. 예약 컨텍스트(누가 진료하는지)를 그대로 활용한다.

    subjective=True: "친절해?/잘 봐?" 같은 주관 평가 질문 — 단정 대신 따뜻한 일반 안내를 붙인다.
    이름을 못 찾아도 절대 '정보가 없습니다'로 끝내지 않는다(유형 4).
    """
    name = await _lookup_vet_name(ctx)
    if name:
        suffix = "" if name.endswith(("선생님", "원장님", "수의사")) else " 선생님"
        if subjective:
            return (
                f"이번 예약은 {name}{suffix}이 맡아요. "
                "친절도나 진료 스타일은 제가 단정해서 말씀드리기 어려워요."
            )
        return f"이번 예약은 {name}{suffix}으로 잡혀 있어요."
    if subjective:
        return (
            "현재 예약에서 담당 수의사 정보는 확인되지 않아요. "
            "친절도나 진료 스타일도 제가 단정해서 말씀드리기 어려워요."
        )
    return (
        "현재 예약에서 담당 수의사 정보는 확인되지 않아요. "
        "병원에 확인해보시는 게 가장 정확해요."
    )


async def _run_pending_action(ctx: SessionContext, action: str) -> AgentResult:
    if ctx.followup_limited and action in {"rebook", "cancel"}:
        return AgentResult(
            reply=BOOKING_CHANGE_LIMITED_REPLY,
            quick_replies=_LIMITED_QUICK_REPLIES,
            state_patch=_patch_pending(""),
        )
    if action == "hospital_info":
        return AgentResult(
            reply=await hospital_info_reply(ctx),
            quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [SCHEDULE_LIST_PILL, NEW_BOOKING_DIRECT_PILL],
            state_patch=_patch_pending(""),
        )
    if action == "appointment_time":
        return AgentResult(
            reply=await appointment_time_reply(ctx),
            quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [REBOOK_ACTION_PILL, SCHEDULE_LIST_PILL, HOSPITAL_INFO_PILL],
            state_patch=_patch_pending(""),
        )
    if action == "vet_info":
        return AgentResult(
            reply=await vet_info_reply(ctx),
            quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [HOSPITAL_INFO_PILL, SCHEDULE_LIST_PILL],
            state_patch=_patch_pending(""),
        )
    if action == "schedule_list":
        return AgentResult(
            reply=REPLY_SCHEDULE_LIST,
            quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [REBOOK_ACTION_PILL, HOSPITAL_INFO_PILL],
            events=[{"type": "list_schedules", "emrid": ctx.emrid}],
            state_patch=_patch_pending(""),
        )
    if action == "new_booking":
        return AgentResult(
            reply=REPLY_NEW_BOOKING_CONFIRM,
            quick_replies=[NEW_BOOKING_DIRECT_PILL, NEW_BOOKING_TRIAGE_PILL],
            state_patch=_patch_pending(""),
        )
    if action == "rebook":
        return AgentResult(
            reply=REPLY_REBOOK,
            events=[{"type": "rebook_request", "emrid": ctx.emrid}],
            state_patch=_patch_pending(""),
        )
    if action == "prep":
        return AgentResult(
            reply=REPLY_PREP_INSTRUCTIONS,
            events=[{"type": "show_prep", "emrid": ctx.emrid}],
            state_patch=_patch_pending(""),
        )
    return AgentResult(state_patch=_patch_pending(""))


def _visit_note_summary_reply(ctx: SessionContext) -> str:
    summary = (ctx.followup_summary or "").strip()
    if summary:
        return (
            "진료 때는 최근 상태 변화와 함께 지금까지 남긴 내용을 차례로 말씀해 주세요. "
            f"요약하면 {summary[:120]}입니다."
        )
    return "진료 때는 증상이 시작된 시점, 오늘 달라진 점, 식욕·배변·기운 변화를 함께 말씀해 주세요."
