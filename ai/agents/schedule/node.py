"""스케줄 노드 (오케스트레이터용).  담당: 리드

문진으로 나온 응급도(triage_resultDB)를 보고 가능한 예약 시간을 추천한다.
실제 슬롯 계산은 기존 crud/schedule.recommend_slots(결정론, DB) 그대로 사용.
※ 슬롯 '확정'은 별도 예약 확정 API에서(여기선 추천까지). AGENT_SPECS §3.
"""
from __future__ import annotations

from sqlalchemy import select

from ai.orchestrator.contracts import AgentResult, SessionContext


def _slot_label(slot) -> str:
    """슬롯 dict를 사람이 보는 짧은 라벨로(키 구조 달라도 안 깨지게 방어적)."""
    if isinstance(slot, dict):
        for k in ("label", "confirmed_time", "datetime", "start", "time", "date"):
            if slot.get(k):
                return str(slot[k])
    return str(slot)


class ScheduleNode:
    name = "schedule"
    description = "응급도 기반으로 가능한 예약 시간을 추천."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        if ctx.db is None or ctx.emrid is None:
            return AgentResult(reply="먼저 증상 문진을 마치면 예약 시간을 추천해드릴게요.")

        # 응급도 읽기 (문진 결과)
        urgency = "GREEN"
        try:
            from app.models.triage_result import TriageResult
            tr = (await ctx.db.execute(
                select(TriageResult).where(TriageResult.emrid == ctx.emrid)
            )).scalars().first()
            if tr:
                urgency = tr.urgency_level or "GREEN"
        except Exception:
            pass

        # 기존 결정론 슬롯 추천 그대로 사용
        slots: list[str] = []
        try:
            from app.crud.schedule import recommend_slots
            rec = await recommend_slots(
                ctx.db, urgency=urgency, duration_min=30, hospitalid=ctx.hospitalid,
            )
            slots = [_slot_label(s) for s in (rec.get("recommended") or [])[:3]]
        except Exception:
            slots = []

        if slots:
            return AgentResult(
                reply="이 시간들 중에 골라주세요. 다른 시간을 원하시면 말씀해 주세요.",
                quick_replies=slots + ["다른 시간"],
            )
        return AgentResult(
            reply="가능한 시간을 찾고 있어요. 원하시는 날짜·시간대를 알려주시면 맞춰볼게요.",
            quick_replies=["오늘", "내일", "이번 주말"],
        )


schedule = ScheduleNode()
