"""경과 필터 AI.  담당: B

예약 뒤(Phase.BOOKED) 보호자 메시지를 보고, '진짜 경과'면 followupDB에 저장하고
잡담·병원질문이면 저장 안 하고 가볍게 넘긴다(필요 시 응대로 handoff).
흐름: 분류(LLM/fallback) → 경과면 누적요약 머지 + followupDB 저장 → AgentResult.
자세한 할 일: docs/AGENT_SPECS.md "6. 필터링".
"""
from __future__ import annotations

from ai.llm import call_llm_json
from ai.monitoring import push_log
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from . import repository
from .prompts import (
    REBOOK_PILL,
    REPLY_CONFIRM_PHOTO,
    REPLY_HOSPITAL_INFO,
    REPLY_IRRELEVANT,
    REPLY_PET_GENERAL,
    REPLY_REBOOK,
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


async def classify_followup(
    ctx: SessionContext,
    user_message: str,
    *,
    vision_findings: str = "",
    vision_relevant: bool | None = None,
):
    """LLM으로 경과 여부 분류. 실패하면 키워드 fallback.

    vision_findings/vision_relevant: 첨부 사진·영상의 VLM 소견(있으면 분류·답변에 반영).
    """
    prompt = build_classification_prompt(
        pet_info=ctx.pet_info,
        followup_summary=ctx.followup_summary,
        history=ctx.history,
        user_message=user_message,
        attachment_count=len(ctx.attachments or []),
        vision_findings=vision_findings,
        vision_relevant=vision_relevant,
    )
    try:
        raw = await call_llm_json(prompt)
    except Exception:
        raw = None
    return parse_classification(raw, user_message)


async def analyze_media(ctx: SessionContext, user_message: str) -> tuple[str, bool | None]:
    """첨부 이미지/영상을 읽어 (소견, 관련성) 반환. triage vision 재사용(fail-open).

    첨부가 없거나 분석 실패 시 ("", None) — 저장/응답 흐름을 막지 않는다.
    """
    if not ctx.attachments:
        return "", None
    try:
        from ai.agents.triage import vision
        vis = await vision.analyze(ctx.attachments, user_message)
    except Exception:
        vis = None
    if not vis:
        return "", None
    findings = (vis.get("note") or "").strip() \
        or ((vis.get("evidence") or {}).get("vlm_description") or "").strip()
    return findings, vis.get("relevant")


class FollowupFilterAgent:
    name = "followup_filter"
    description = "예약 후 경과 보고를 걸러서, 진짜 경과면 followupDB에 저장하고 잡담이면 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        user_message = (args or {}).get("user_message") or ctx.user_message or ""
        has_media = bool(ctx.attachments)
        # 사진·영상을 먼저 읽어, 분류·답변·요약에 소견을 반영한다(없으면 빈값).
        vision_findings, vision_relevant = await analyze_media(ctx, user_message)
        cls = await classify_followup(
            ctx, user_message,
            vision_findings=vision_findings, vision_relevant=vision_relevant,
        )
        is_saved = False

        # 재예약(예약 변경/앞당김) 의도 — LLM 판단 또는 '더 빠른 시간 찾기' pill 클릭.
        # 경과 보고가 아닐 때만 예약 흐름으로 넘긴다(증상 경과는 저장이 우선).
        wants_rebook = (cls.wants_rebooking or user_message.strip() == REBOOK_PILL) and not cls.is_followup

        # 텍스트가 경과도 아닌데 사진이 '무관해 보이면'(relevant=false) → 잘못 보낸 것일 수 있으니
        # 저장하지 말고 한 번 더 확인한다(맞으면 다시 보내달라). 데이터 오염/오알람 방지.
        photo_missent = has_media and (not cls.is_followup) and (vision_relevant is False)

        # 0) 재예약 요청 → 저장하지 않고 예약 흐름 신호(rebook_request)를 프론트로 넘긴다.
        if wants_rebook:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_REBOOK),
                events=[{"type": "rebook_request", "emrid": ctx.emrid}],
            )
        # 1) 저장하지 않는 경우: (경과 아님 + 첨부 없음) 또는 (잘못 보낸 듯한 사진).
        elif (not cls.is_followup and not has_media) or photo_missent:
            if photo_missent:
                result = AgentResult(reply=ensure_safe_reply(cls, REPLY_CONFIRM_PHOTO))
            elif cls.category == Category.HOSPITAL_INFO:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_HOSPITAL_INFO),
                    handoff=Intent.RECEPTION,
                )
            elif cls.category == Category.PET_GENERAL:
                result = AgentResult(reply=ensure_safe_reply(cls, REPLY_PET_GENERAL))
            else:
                result = AgentResult(reply=ensure_safe_reply(cls, REPLY_IRRELEVANT))

        else:
            # 2) 저장할 경과 메모(delta) 결정.
            delta = (cls.summary_delta or "").strip()
            if not delta:
                delta = user_message.strip()[:100] if user_message.strip() else "보호자가 상태 사진·영상을 공유함."
            # 사진 소견을 차트 요약에 보강(LLM이 빠뜨렸을 때만 — 중복 방지).
            if vision_findings and vision_findings not in delta:
                delta = f"{delta} / {vision_findings}".strip(" /")
            updated_summary = merge_followup_summary(ctx.followup_summary, delta)

            # 3) followupDB 저장.
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
            is_saved = saved is not None

            # 사진 소견을 반영한 LLM 답변(assistant_reply) 우선, 비면 상황별 캔드 멘트로.
            reply = ensure_safe_reply(cls, REPLY_SAVED if cls.is_followup else REPLY_SAVED_MEDIA)
            events = []
            if is_saved:
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
            # urgent면 진료를 앞당기는 '더 빠른 시간 찾기' pill을 제안(클릭 시 재예약 흐름).
            result = AgentResult(
                reply=reply,
                quick_replies=[REBOOK_PILL] if emergency else [],
                state_patch={"followup_summary": updated_summary},
                events=events,
            )

        # 공통 모니터링 로그
        push_log("followup_filter", {
            "scheduleid": ctx.scheduleid,
            "message": user_message[:80],
            "category": cls.category.value,
            "severity": cls.severity_hint.value,
            "is_saved": is_saved,
            "has_media": has_media,
        })

        return result


followup_filter = FollowupFilterAgent()
