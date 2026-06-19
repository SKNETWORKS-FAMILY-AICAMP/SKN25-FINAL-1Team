"""응대(병원 안내) AI.  담당: A

하는 일: 병원 정보(위치·시간·전화·수의사) 알려주기, 가벼운 질문은 조심스럽게 안내,
        증상 같으면 문진으로 넘기는 신호(handoff)만 준다.
지금은 DB에서 병원 정보를 직접 읽어 프롬프트로 답을 만든다. (MCP는 나중에 감쌈)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, select

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, SessionContext

from .prompts import RECEPTION_SYSTEM

_DOCTOR_KW   = ("의사", "선생님", "수의사", "원장", "누구", "담당")
_SCHEDULE_KW = ("시간", "운영", "휴진", "점심", "몇 시", "몇시", "언제", "오늘", "영업")
_PROFILE_KW  = ("소개", "특징", "어떤", "어떻게", "설명", "정보")
_PHONE_KW    = ("전화", "번호", "연락", "문의")
_ADDRESS_KW  = ("주소", "위치", "어디", "찾아", "오시는", "길")


def _prev_was_vet_intro(history: list) -> bool:
    """직전 봇 답변이 수의사 소개였는지 확인."""
    for m in reversed(history or []):
        if m.get("role") == "assistant":
            content = m.get("content", "")
            return any(k in content for k in ("수의사", "선생님이 계세요", "전문으로"))
    return False


async def _hospital_facts(db, hospitalid: int | None, question: str,
                          history: list | None = None) -> str:
    """질문 키워드에 맞는 병원 정보만 조합해 반환."""
    if not db or not hospitalid:
        return "등록된 병원 정보가 없습니다."

    from app.models.doctor import Doctor
    from app.models.doctor_profile import DoctorProfile
    from app.models.hospital import Hospital
    from app.models.hospital_profile import HospitalProfile
    from app.models.vet_schedule import HospitalClosedDate, HospitalWeeklySchedule, VetWeeklySchedule

    hos = (await db.execute(select(Hospital).where(Hospital.hospitalid == hospitalid))).scalar_one_or_none()
    if not hos:
        return "등록된 병원 정보가 없습니다."

    q = question or ""
    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    lines = [f"병원명: {hos.hospital_name}"]

    if any(k in q for k in _ADDRESS_KW):
        lines.append(f"주소: {hos.hospital_address or '미등록'}")
    if any(k in q for k in _PHONE_KW):
        lines.append(f"전화: {hos.hospital_number or '미등록'}")

    # 아무 키워드도 없으면 주소+전화 둘 다 포함 (병원이 어디야? 같은 짧은 질문 대비)
    if not any(k in q for k in _ADDRESS_KW + _PHONE_KW + _DOCTOR_KW + _SCHEDULE_KW + _PROFILE_KW):
        lines.append(f"주소: {hos.hospital_address or '미등록'}")
        lines.append(f"전화: {hos.hospital_number or '미등록'}")

    # 의사 관련 질문
    if any(k in q for k in _DOCTOR_KW):
        doctors = (await db.execute(
            select(Doctor).where(Doctor.hospitalid == hospitalid, Doctor.is_active == True)
        )).scalars().all()
        if doctors:
            lines.append("수의사 소개:")
            for d in doctors:
                profile = (await db.execute(
                    select(DoctorProfile).where(DoctorProfile.doctorid == d.doctorid)
                )).scalar_one_or_none()
                desc = f"{d.doctor_name} 수의사"
                if profile:
                    if profile.specialty:
                        desc += f" / 전문진료: {profile.specialty}"
                    if profile.specialty_areas:
                        desc += f" / 분야: {', '.join(profile.specialty_areas)}"
                lines.append(desc)
                # 의사별 요일 스케줄
                vet_scheds = (await db.execute(
                    select(VetWeeklySchedule).where(VetWeeklySchedule.doctorid == d.doctorid)
                )).scalars().all()
                for vs in sorted(vet_scheds, key=lambda x: x.day_of_week):
                    day = day_names[vs.day_of_week]
                    if not vs.is_open:
                        lines.append(f"  {day}: 휴진")
                    elif vs.start_time and vs.end_time:
                        lunch = f" / 점심 {vs.lunch_start}~{vs.lunch_end}" if vs.lunch_start and vs.lunch_end else ""
                        lines.append(f"  {day}: {vs.start_time}~{vs.end_time}{lunch}")

    # 운영시간 관련 질문
    if any(k in q for k in _SCHEDULE_KW):
        today = datetime.now().weekday()
        # 직전 봇 답변이 수의사 소개였으면 수의사별 진료시간, 아니면 병원 전체 운영시간
        if _prev_was_vet_intro(history):
            doctors = (await db.execute(
                select(Doctor).where(Doctor.hospitalid == hospitalid, Doctor.is_active == True)
            )).scalars().all()
            lines.append("수의사별 진료시간:")
            for d in doctors:
                vet_scheds = (await db.execute(
                    select(VetWeeklySchedule).where(VetWeeklySchedule.doctorid == d.doctorid)
                )).scalars().all()
                if not vet_scheds:
                    continue
                lines.append(f"{d.doctor_name} 선생님:")
                for vs in sorted(vet_scheds, key=lambda x: x.day_of_week):
                    day = day_names[vs.day_of_week]
                    mark = "(오늘)" if vs.day_of_week == today else ""
                    if not vs.is_open:
                        lines.append(f"  {day}{mark}: 휴진")
                    elif vs.start_time and vs.end_time:
                        lunch = f" / 점심 {vs.lunch_start}~{vs.lunch_end}" if vs.lunch_start and vs.lunch_end else ""
                        lines.append(f"  {day}{mark}: {vs.start_time}~{vs.end_time}{lunch}")
        else:
            schedules = (await db.execute(
                select(HospitalWeeklySchedule).where(HospitalWeeklySchedule.hospitalid == hospitalid)
            )).scalars().all()
            lines.append("운영시간:")
            for wk in sorted(schedules, key=lambda x: x.day_of_week):
                day = day_names[wk.day_of_week]
                mark = "(오늘)" if wk.day_of_week == today else ""
                if not wk.is_open:
                    lines.append(f"{day}요일{mark}: 휴진")
                elif wk.start_time and wk.end_time:
                    lunch = f" / 점심 {wk.lunch_start}~{wk.lunch_end}" if wk.lunch_start and wk.lunch_end else ""
                    lines.append(f"{day}요일{mark}: {wk.start_time}~{wk.end_time}{lunch}")
            upcoming = (await db.execute(
                select(HospitalClosedDate).where(
                    and_(
                        HospitalClosedDate.hospitalid == hospitalid,
                        HospitalClosedDate.date >= date.today(),
                        HospitalClosedDate.date <= date.today() + timedelta(days=30),
                    )
                )
            )).scalars().all()
            if upcoming:
                lines.append("임시 휴진일: " + ", ".join(str(c.date) for c in upcoming))

    # 병원 소개·특징 관련 질문
    if any(k in q for k in _PROFILE_KW):
        profile = (await db.execute(
            select(HospitalProfile).where(HospitalProfile.hospitalid == hospitalid)
        )).scalar_one_or_none()
        if profile:
            if profile.tagline:
                lines.append(f"병원 소개: {profile.tagline}")
            if profile.features:
                lines.append(f"병원 특징: {', '.join(profile.features)}")
            if profile.intro:
                lines.append(f"상세 소개: {profile.intro}")

    return "\n".join(lines)


class ReceptionAgent:
    name = "reception"
    description = "병원 정보 안내 담당. 진단·처방 같은 진료 얘기는 '수의사께'로 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        facts = await _hospital_facts(ctx.db, ctx.hospitalid, ctx.user_message, ctx.history)
        pet_name = ctx.pet_info.get("name") or "아이"
        streak = (ctx.reception_streak or 0) + 1

        # 최근 대화 히스토리 (최대 6개 turn)
        history_lines = []
        for m in (ctx.history or [])[-6:]:
            role = "보호자" if m.get("role") == "user" else "봇"
            history_lines.append(f"{role}: {m.get('content', '')}")
        history_block = "\n[이전 대화]\n" + "\n".join(history_lines) + "\n" if history_lines else ""

        prompt = (
            f"{RECEPTION_SYSTEM}\n"
            f"반려동물 이름은 '{pet_name}'야. 이름에 맞는 조사를 자연스럽게 써줘.\n\n"
            f"[우리 병원 정보]\n{facts}"
            f"{history_block}\n"
            f"[보호자 말]\n{ctx.user_message}\n\n"
            '반드시 JSON으로만 답해: {"reply": "답변 텍스트", "pills": ["버튼1", "버튼2"]}'
        )

        try:
            out = await call_llm_json(prompt)
            reply = out.get("reply") or ""
            raw_pills = out.get("pills") or []
            quick_replies = [p for p in raw_pills if isinstance(p, str) and p.strip()][:4]
        except Exception:
            reply = "지금 정보를 불러오지 못했어요. 잠시 후 다시 시도하거나 병원에 직접 문의해 주세요."
            quick_replies = []

        return AgentResult(
            reply=reply,
            quick_replies=quick_replies,
            state_patch={"reception_streak": streak},
        )


reception = ReceptionAgent()
