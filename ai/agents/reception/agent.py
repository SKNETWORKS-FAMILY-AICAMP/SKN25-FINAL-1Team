"""응대(병원 안내) AI.  담당: A

하는 일: 병원 정보(위치·시간·전화·수의사) 알려주기, 가벼운 질문은 조심스럽게 안내,
        증상 같으면 문진으로 넘기는 신호(handoff)만 준다.
지금은 DB에서 병원 정보를 직접 읽어 프롬프트로 답을 만든다. (MCP는 나중에 감쌈)
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta

from sqlalchemy import and_, select

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, Flow, SessionContext

from .prompts import build_reception_prompt

logger = logging.getLogger(__name__)

_CLOSING_QUESTIONS = [
    "또 궁금한 점 있으신가요?",
    "다른 것도 도와드릴까요?",
    "더 궁금한 게 있으시면 말씀해 주세요!",
    "혹시 더 필요한 정보 있으세요?",
    "다른 것도 알고 싶으신 게 있나요?",
]

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

    is_schedule_q = any(k in q for k in _SCHEDULE_KW)
    is_doctor_q   = any(k in q for k in _DOCTOR_KW)

    # 의사 소개 질문 (시간 질문이 아닐 때만 bio 노출)
    if is_doctor_q and not is_schedule_q:
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
                if profile and profile.bio:
                    desc += f" / {profile.bio}"
                lines.append(desc)

    # 운영시간 관련 질문
    if is_schedule_q:
        today = datetime.now().weekday()
        # 의사 키워드 포함이거나 직전 봇 답변이 수의사 소개였으면 수의사별 진료시간
        if is_doctor_q or _prev_was_vet_intro(history):
            doctors = (await db.execute(
                select(Doctor).where(Doctor.hospitalid == hospitalid, Doctor.is_active == True)
            )).scalars().all()
            def fmt_t(t) -> str:
                return str(t)[:5] if t else ""

            sched_lines = ["[진료시간 — 아래 텍스트를 reply에 그대로 포함할 것. 절대 문장으로 바꾸지 마]"]
            first_doc = True
            for d in doctors:
                vet_scheds = (await db.execute(
                    select(VetWeeklySchedule).where(VetWeeklySchedule.doctorid == d.doctorid)
                )).scalars().all()
                if not vet_scheds:
                    continue
                if not first_doc:
                    sched_lines.append("")  # 의사 사이 빈 줄
                first_doc = False
                sched_lines.append(f"{d.doctor_name} 선생님:")
                for vs in sorted(vet_scheds, key=lambda x: x.day_of_week):
                    day = day_names[vs.day_of_week]
                    mark = "(오늘)" if vs.day_of_week == today else ""
                    if not vs.is_open:
                        sched_lines.append(f"  {day}{mark}: 휴진")
                    elif vs.start_time and vs.end_time:
                        lunch = f" (점심 {fmt_t(vs.lunch_start)}~{fmt_t(vs.lunch_end)})" if vs.lunch_start and vs.lunch_end else ""
                        sched_lines.append(f"  {day}{mark}: {fmt_t(vs.start_time)}~{fmt_t(vs.end_time)}{lunch}")
            sched_lines.append("[/진료시간]")
            lines.extend(sched_lines)
        else:
            schedules = (await db.execute(
                select(HospitalWeeklySchedule).where(HospitalWeeklySchedule.hospitalid == hospitalid)
            )).scalars().all()
            def fmt_t(t) -> str:
                return str(t)[:5] if t else ""

            sched_lines = ["[운영시간 — 아래 텍스트를 reply에 그대로 포함할 것. 절대 문장으로 바꾸지 마]"]
            for wk in sorted(schedules, key=lambda x: x.day_of_week):
                day = day_names[wk.day_of_week]
                mark = "(오늘)" if wk.day_of_week == today else ""
                if not wk.is_open:
                    sched_lines.append(f"{day}{mark}: 휴진")
                elif wk.start_time and wk.end_time:
                    lunch = f" (점심 {fmt_t(wk.lunch_start)}~{fmt_t(wk.lunch_end)})" if wk.lunch_start and wk.lunch_end else ""
                    sched_lines.append(f"{day}{mark}: {fmt_t(wk.start_time)}~{fmt_t(wk.end_time)}{lunch}")
            sched_lines.append("[/운영시간]")
            lines.extend(sched_lines)
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
        # 병원 정보 수집 — MCP 도구를 LLM이 골라 호출(우선), 실패 시 키워드 DB 조회로 폴백.
        facts = await self._collect_facts(ctx)
        pet_name = ctx.pet_info.get("name") or "아이"
        streak = (ctx.reception_streak or 0) + 1

        history_lines = [
            f"{'보호자' if m.get('role') == 'user' else '봇'}: {m.get('content', '')}"
            for m in (ctx.history or [])[-6:]
        ]
        history_block = "\n[이전 대화]\n" + "\n".join(history_lines) + "\n" if history_lines else ""
        streak_hint = f"\n[현재 안내 횟수: {streak}회 — 이미 안내한 적 있음]" if streak >= 2 else ""

        # 문진 중 잠깐 들른 '병원 정보 우회'면 → 답한 뒤 자연스럽게 증상 문진으로 돌아오도록 마무리.
        if ctx.active_flow == Flow.TRIAGING:
            streak_hint += (
                f"\n[중요] 보호자는 원래 '{pet_name} 증상 문진' 중이고 잠깐 병원 정보를 물은 거야. "
                f"병원 정보를 친절히 답한 뒤, 마지막은 '다른 것도 도와드릴까요?' 대신 증상 이야기로 "
                f"자연스럽게 돌아오도록 권해(예: '그럼 {pet_name} 증상 더 들려주실래요?')."
            )

        prompt = build_reception_prompt(facts, pet_name, history_block, streak_hint, ctx.user_message)

        try:
            out = await call_llm_json(prompt)
            reply = out.get("reply") or ""
            raw_pills = out.get("pills") or []
            quick_replies = [p for p in raw_pills if isinstance(p, str) and p.strip()][:4]
        except Exception:
            reply = "지금 정보를 불러오지 못했어요. 잠시 후 다시 시도하거나 병원에 직접 문의해 주세요."
            quick_replies = []

        # 마무리 확인 문장이 없으면 강제로 추가
        _CLOSING_KW = ("말씀해 주세요", "있으신가요", "도와드릴까요", "알려주세요",
                       "찾아주세요", "연락주세요", "궁금한 점", "궁금한 게")
        last_line = reply.rstrip().split("\n")[-1] if reply else ""
        if reply and not last_line.endswith("?") and not any(k in last_line for k in _CLOSING_KW):
            reply = reply.rstrip() + "\n\n" + random.choice(_CLOSING_QUESTIONS)

        return AgentResult(
            reply=reply,
            quick_replies=quick_replies,
            state_patch={"reception_streak": streak},
        )

    # 병원 정보 수집: MCP 도구(LLM tool-calling) 우선, 실패/미가동 시 키워드 DB 조회 폴백.
    async def _collect_facts(self, ctx: SessionContext) -> str:
        try:
            from ai.orchestrator.mcp.client import get_mcp_tools
            tools = await get_mcp_tools()
        except Exception as e:
            logger.warning("[reception] MCP 도구 로드 실패, 폴백: %s", e)
            tools = []
        if tools:
            try:
                # MCP 가동 중이면 LLM이 고른 도구 결과(없으면 빈 문자열)를 그대로 사용.
                return await self._gather_via_tools(ctx, tools)
            except Exception as e:
                logger.warning("[reception] MCP gather 실패, 폴백: %s", e)
        return await _hospital_facts(ctx.db, ctx.hospitalid, ctx.user_message, ctx.history)

    # LLM이 질문을 보고 필요한 MCP 도구를 스스로 호출 → 수집한 사실 텍스트 반환.
    async def _gather_via_tools(self, ctx: SessionContext, tools: list) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        from langchain_openai import ChatOpenAI

        from ai.llm import _resolve_model

        by_name = {t.name: t for t in tools}
        llm = ChatOpenAI(model=_resolve_model(), temperature=0).bind_tools(tools)
        sys = (
            "너는 동물병원 안내를 위한 '정보 수집기'야. 보호자 질문에 답하는 데 필요한 사실만 "
            "제공된 도구를 호출해 모아라. 진단·처방·증상 판단은 도구로 모으지 마(수의사 몫). "
            f"현재 병원 ID는 {ctx.hospitalid}, 반려동물 ID는 {ctx.petid}야. 도구 인자에 이 ID를 써. "
            "병원 정보가 필요 없는 질문이면 도구를 호출하지 마."
        )
        messages = [SystemMessage(content=sys), HumanMessage(content=ctx.user_message or "")]
        collected: list[str] = []
        for _ in range(3):  # 도구 호출 루프 (무한루프 방지)
            ai = await llm.ainvoke(messages)
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break
            for tc in tool_calls:
                tool = by_name.get(tc["name"])
                if tool is None:
                    continue
                try:
                    out = await tool.ainvoke(tc["args"])
                except Exception as e:
                    out = f"(도구 실패: {e})"
                collected.append(f"[{tc['name']}] {out}")
                messages.append(ToolMessage(content=str(out)[:2000], tool_call_id=tc["id"]))
        if collected:
            logger.info("[reception] MCP 도구 %s회 호출", len(collected))
        return "\n".join(collected)


reception = ReceptionAgent()
