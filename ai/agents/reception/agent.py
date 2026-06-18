"""응대(병원 안내) AI.  담당: A

하는 일: 병원 정보(위치·시간·전화) 알려주기, 가벼운 질문은 조심스럽게 안내,
        증상 같으면 문진으로 넘기는 신호(handoff)만 준다.
지금은 DB에서 병원 정보를 직접 읽어 프롬프트로 답을 만든다. (MCP는 나중에 감쌈)
자세한 할 일: docs/AGENT_SPECS.md "1. 응대".
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ai.llm import call_llm
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from .prompts import RECEPTION_SYSTEM


async def _hospital_facts(db, hospitalid: int | None) -> str:
    """병원 기본정보 + 오늘 운영시간을 한 덩어리 텍스트로. (응대 프롬프트에 넣음)"""
    if not db or not hospitalid:
        return "등록된 병원 정보가 없습니다."
    from app.models.hospital import Hospital
    from app.models.vet_schedule import HospitalWeeklySchedule

    hos = (await db.execute(select(Hospital).where(Hospital.hospitalid == hospitalid))).scalar_one_or_none()
    if not hos:
        return "등록된 병원 정보가 없습니다."
    lines = [f"이름: {hos.hospital_name}",
             f"주소: {hos.hospital_address or '미등록'}",
             f"전화: {hos.hospital_number or '미등록'}"]
    # 오늘 요일 운영시간 (day_of_week 규약은 DB 기준 — 그대로 매칭)
    today = datetime.now().weekday()
    wk = (await db.execute(
        select(HospitalWeeklySchedule).where(
            HospitalWeeklySchedule.hospitalid == hospitalid,
            HospitalWeeklySchedule.day_of_week == today,
        )
    )).scalar_one_or_none()
    if wk and wk.is_open and wk.start_time and wk.end_time:
        lines.append(f"오늘 운영: {wk.start_time}~{wk.end_time}")
    elif wk and not wk.is_open:
        lines.append("오늘은 휴진")
    return "\n".join(lines)


class ReceptionAgent:
    name = "reception"
    description = "병원 정보 안내 담당. 진단·처방 같은 진료 얘기는 '수의사께'로 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        facts = await _hospital_facts(ctx.db, ctx.hospitalid)
        prompt = (
            f"{RECEPTION_SYSTEM}\n\n"
            f"[우리 병원 정보]\n{facts}\n\n"
            f"[보호자 말]\n{ctx.user_message}\n\n"
            "위 정보로 친절히 한국어로 답해줘. 모르는 건 '병원에 문의해 주세요'라고 안내해."
        )
        try:
            reply = await call_llm(prompt)
        except Exception:
            reply = "지금 정보를 불러오지 못했어요. 잠시 후 다시 시도하거나 병원에 직접 문의해 주세요."

        # 응대만 2번 이상 이어지면 문진/예약으로 슬쩍 안내 (AGENT_SPECS §5.3)
        streak = (ctx.reception_streak or 0) + 1
        quick_replies: list[str] = []
        if streak >= 2:
            name = ctx.pet_info.get("name") or "아이"
            reply += f"\n\n혹시 {name}가 아픈 거면 증상을 알려주세요. 예약까지 도와드릴게요!"
            quick_replies = ["증상 말하기", "예약하기"]

        return AgentResult(
            reply=reply,
            quick_replies=quick_replies,
            state_patch={"reception_streak": streak},
        )


reception = ReceptionAgent()
