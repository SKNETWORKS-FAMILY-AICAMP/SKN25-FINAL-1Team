"""경과 필터 AI.  담당: B

예약 뒤(Phase.BOOKED) 보호자 메시지를 보고, '진짜 경과'면 followupDB에 저장하고
잡담·병원질문이면 저장 안 하고 가볍게 넘긴다(필요 시 응대로 handoff).
흐름: 분류(LLM/fallback) → 경과면 누적요약 머지 + followupDB 저장 → AgentResult.
자세한 할 일: docs/AGENT_SPECS.md "6. 필터링".
"""
from __future__ import annotations

from ai.llm import call_llm_json
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from . import repository
from .prompts import (
    REPLY_HOSPITAL_INFO,
    REPLY_IRRELEVANT,
    REPLY_PET_GENERAL,
    REPLY_SAVED,
    REPLY_SAVED_MEDIA,
    build_classification_prompt,
)
from .schema import (
    Category,
    SeverityHint,
    ensure_safe_reply,
    merge_followup_summary,
    parse_classification,
)


async def classify_followup(ctx: SessionContext, user_message: str):
    """LLM으로 경과 여부 분류. 실패하면 키워드 fallback."""
    prompt = build_classification_prompt(
        pet_info=ctx.pet_info,
        followup_summary=ctx.followup_summary,
        history=ctx.history,
        user_message=user_message,
        attachment_count=len(ctx.attachments or []),
    )
    try:
        raw = await call_llm_json(prompt)
    except Exception:
        raw = None
    return parse_classification(raw, user_message)


class FollowupFilterAgent:
    name = "followup_filter"
    description = "예약 후 경과 보고를 걸러서, 진짜 경과면 followupDB에 저장하고 잡담이면 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        # 메시지는 보통 ctx.user_message 로 들어온다(그래프가 args={} 로 호출).
        user_message = (args or {}).get("user_message") or ctx.user_message or ""

        cls = await classify_followup(ctx, user_message)

        # 사진·영상이 첨부되면 분류 결과와 무관하게 무조건 경과로 저장한다.
        # (보호자가 상태 사진/영상을 보낸 것 자체가 경과 공유 의도 — 글이 애매하거나
        #  질문형이어도 의료진이 봐야 하므로 남긴다.)
        has_media = bool(ctx.attachments)

        # 1) 경과도 아니고 첨부도 없으면 저장하지 않고 분기별 안내.
        if not cls.is_followup and not has_media:
            if cls.category == Category.HOSPITAL_INFO:
                return AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_HOSPITAL_INFO),
                    handoff=Intent.RECEPTION,
                )
            if cls.category == Category.PET_GENERAL:
                return AgentResult(reply=ensure_safe_reply(cls, REPLY_PET_GENERAL))
            return AgentResult(reply=ensure_safe_reply(cls, REPLY_IRRELEVANT))

        # 2) 저장할 경과 메모(delta) 결정.
        #    - 글이 경과로 잡혔으면 LLM 요약 사용
        #    - 비었으면(첨부만 등) 사용자 글, 그것도 없으면 미디어 공유 문구
        delta = (cls.summary_delta or "").strip()
        if not delta:
            delta = user_message.strip()[:100] if user_message.strip() else "보호자가 상태 사진·영상을 공유함."
        updated_summary = merge_followup_summary(ctx.followup_summary, delta)

        # 3) followupDB 저장 (FK=emrid, userid NOT NULL).
        #    urgent_possible 만 emergency_alert 로 표시(진짜 응급 가능성).
        emergency = cls.severity_hint == SeverityHint.URGENT_POSSIBLE
        saved = await repository.save_followup(
            ctx.db,
            emrid=ctx.emrid,
            userid=ctx.userid,
            message=user_message,
            images=ctx.attachments,
            ai_summary=updated_summary,
            emergency_alert=emergency,
        )

        # 4) 보호자 응답.
        #    - 글이 경과면 LLM assistant_reply 우선(+urgent 안전문구 보정)
        #    - 첨부 때문에 저장하는 경우엔 비경과 멘트 대신 '잘 받았어요' 류
        if cls.is_followup:
            reply = ensure_safe_reply(cls, REPLY_SAVED)
        else:
            reply = REPLY_SAVED_MEDIA

        events = []
        if saved is not None:
            events.append({
                "type": "followup_saved",
                "emrid": ctx.emrid,
                "followupid": getattr(saved, "followupid", None),
                "category": cls.category.value,
                "severity_hint": cls.severity_hint.value,
                "emergency": emergency,
                "has_media": has_media,
                "forced_by_media": has_media and not cls.is_followup,
            })

        return AgentResult(
            reply=reply,
            quick_replies=["빠른 예약 확인"] if emergency else [],
            state_patch={"followup_summary": updated_summary},
            events=events,
        )


followup_filter = FollowupFilterAgent()
