"""경과 필터 AI.  담당: B

예약 뒤 보호자 메시지(글·사진·영상)를 보고, '진짜 경과'면 followupDB에 저장하고
잡담이면 저장 안 하고 가볍게 넘긴다.
자세한 할 일: docs/AGENT_SPECS.md "6. 필터링".
"""
from __future__ import annotations

import json

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, SessionContext

from .prompts import GUARDIAN_REPLY, RELEVANCE_CHECK, SUMMARY_UPDATE


class FollowupFilterAgent:
    name = "followup_filter"
    description = "예약 후 경과 보고를 걸러서, 진짜 경과면 followupDB에 저장하고 잡담이면 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        prompt = (
            f"{RELEVANCE_CHECK}\n{SUMMARY_UPDATE}\n{GUARDIAN_REPLY}\n\n"
            f"[이전 누적 경과 메모]\n{ctx.followup_summary or '아직 없음'}\n\n"
            f"[이번 보호자 메시지]\n{ctx.user_message}\n"
            f"[첨부 개수] {len(ctx.attachments or [])}\n\n"
            "아래 JSON으로만 답해:\n"
            '{"related": true/false, "ai_summary": "누적 경과 한 줄(관련 없으면 빈 문자열)", '
            '"emergency": true/false, "reply": "보호자에게 보일 공감 한두 문장"}'
        )
        try:
            out = await call_llm_json(prompt)
        except Exception:
            return AgentResult(reply="경과 잘 받았어요. 상태가 달라지면 또 알려주세요.")

        related = bool(out.get("related"))
        reply = out.get("reply") or "경과 잘 받았어요."

        if not related:
            # 잡담 → 저장 안 함
            return AgentResult(reply=reply)

        ai_summary = (out.get("ai_summary") or "").strip()
        emergency = bool(out.get("emergency"))

        # followupDB에 한 행 적재 (경과 본체 저장처)
        if ctx.db is not None and ctx.emrid is not None:
            try:
                from app.models.followup import Followup
                ctx.db.add(Followup(
                    emrid=ctx.emrid,
                    userid=ctx.userid,
                    images=ctx.attachments or [],
                    message=ctx.user_message,
                    ai_summary=ai_summary,
                    emergency_alert=emergency,
                ))
                await ctx.db.commit()
            except Exception:
                await ctx.db.rollback()

        quick = ["빠른 예약 확인"] if emergency else []
        return AgentResult(
            reply=reply,
            quick_replies=quick,
            state_patch={"followup_summary": ai_summary or ctx.followup_summary},
        )


followup_filter = FollowupFilterAgent()
