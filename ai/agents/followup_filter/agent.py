"""경과 필터 AI.  담당: B

예약 뒤(Phase.BOOKED) 보호자 메시지를 보고, '진짜 경과'면 followupDB에 저장하고
잡담·병원질문이면 저장 안 하고 가볍게 넘긴다(필요 시 응대로 handoff).
흐름: 분류(LLM/fallback) → 경과면 누적요약 머지 + followupDB 저장 → AgentResult.
자세한 할 일: docs/AGENT_SPECS.md "6. 필터링".
"""
from __future__ import annotations

import re

from ai.llm import call_llm_json
from ai.monitoring import push_log
from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from . import repository
from .prompts import (
    CLARIFY_QUICK_REPLIES,
    CONTINUE_STATUS_PILL,
    HOSPITAL_INFO_PILL,
    NEW_BOOKING_DIRECT_PILL,
    NEW_BOOKING_TRIAGE_PILL,
    PREP_INSTRUCTIONS_PILL,
    REBOOK_ACTION_PILL,
    REBOOK_PILL,
    REPLY_CANCEL,
    REPLY_CANCEL_POLICY,
    REPLY_CARE_METHOD,
    REPLY_CONFIRM_PHOTO,
    REPLY_EMOTION_ACK,
    REPLY_HOSPITAL_INFO,
    REPLY_IRRELEVANT,
    REPLY_NEW_BOOKING_CONFIRM,
    REPLY_PET_GENERAL,
    REPLY_PREP_INSTRUCTIONS,
    REPLY_REBOOK,
    REPLY_SCHEDULE_LIST,
    SCHEDULE_LIST_PILL,
    START_TRIAGE_REPLY,
    VISIT_NOTE_SUMMARY_PILL,
    build_classification_prompt,
    build_species_mismatch_reply,
    canon_species,
    is_photo_followup,
    last_assistant_question,
    pick_saved_reply,
    short_answer_kind,
)
from app.utils.followup_policy import BOOKING_CHANGE_LIMITED_REPLY, FOLLOWUP_LIMITED_REPLY

# 사진 속 동물과 등록 펫의 종 대조 — 둘 다 이 집합 안에서 확실할 때만 불일치로 판정.
_KNOWN_SPECIES = {"dog", "cat", "rabbit"}
_AFFIRMATIVE_SHORTS = {
    "확인해줘", "확인해 줘", "확인", "응", "네", "그래", "좋아", "보여줘", "보여 줘",
    "해줘", "해 줘", "응 보여줘", "네 보여줘", "그래 보여줘", "응 확인해줘",
}
_REQUEST_ENDINGS = ("알려주세요", "함께 알려주세요", "말씀해 주세요", "말씀해주세요")
# 병원 인물(수의사/원장 등) 질문 감지 — 사실(누구) vs 주관 평가(친절해?/잘 봐?)를 가른다.
_VET_PERSON_WORDS = ("수의사", "의사", "담당", "선생님", "원장")
_VET_FACTUAL_WORDS = ("누구", "누가", "누군", "어떤", "어느", "이름")
_VET_SUBJECTIVE_WORDS = ("친절", "잘 봐", "잘봐", "잘 보", "잘보", "실력", "괜찮", "어때", "좋", "믿", "꼼꼼", "유명", "잘하")
# 예약 '병원/장소' 질문 — '어느 병원'은 시간이 아니라 병원 질문(시간 분기보다 우선).
_HOSPITAL_LOC_WORDS = (
    "어느 병원", "무슨 병원", "어디 병원", "어떤 병원", "병원 이름", "병원이름", "병원 위치",
    "병원 어디", "병원이 어디", "어느 병원으로", "어디로 예약", "병원 주소", "위치", "주소",
)
# 취소: 실제 '실행' 의도 vs '문의/가정형' 구분(가정형은 cancel_request 금지).
_CANCEL_EXEC_WORDS = (
    "취소해줘", "취소해 줘", "취소할래", "취소할게", "취소하고 싶", "취소해주세요", "취소해 주세요",
    "취소합니다", "취소해야", "없애줘", "없애 줘", "취소 부탁",
)
_CANCEL_INQUIRY_MARKS = (
    "하면", "해도", "가능", "되나요", "될까", "돼요", "되요", "수수료", "환불",
    "어떻게", "다시 예약", "다시 잡", "정책", "괜찮", "수 있", "건가요",
)
_ENDING_ALTERNATIVES = (
    "지금 보이는 모습이 더 달라지는지 지켜봐 주세요.",
    "그때 이어서 남겨 주세요.",
    "함께 살펴봐 주세요.",
    "붉어지는 범위나 진물 여부를 함께 살펴봐 주세요.",
)
_LIMITED_QUICK_REPLIES = [
    HOSPITAL_INFO_PILL,
    SCHEDULE_LIST_PILL,
    PREP_INSTRUCTIONS_PILL,
    CONTINUE_STATUS_PILL,
    VISIT_NOTE_SUMMARY_PILL,
]


# 관리방법 질문(상태보고 아님) — '해도 되나/어떻게 관리'. clarify로 새지 않게 한다.
_CARE_METHOD_WORDS = (
    "양치", "칫솔", "씻겨", "씻어", "목욕", "헹궈", "헹구", "닦아", "닦여", "빗겨", "발라",
    "관리", "산책", "먹여도", "그냥 둬", "둬도", "해줘야", "해줘도",
)
_CARE_Q_MARKS = ("되나", "되요", "돼요", "돼", "될까", "해야", "해도", "줘도", "어떻게", "뭘 해", "뭐 해",
                 "하나요", "하나", "할까", "?")
# 감정 표현 — 공감 먼저, clarify 금지.
_EMOTION_WORDS = ("걱정", "불안", "무서", "겁나", "겁이", "속상", "눈물", "마음이", "신경 쓰", "신경쓰",
                  "괜찮은 거 맞", "괜찮은거 맞", "별일 아니", "안심", "초조", "무섭")
# 반복 관찰안내 종결 — 3턴 연속이면 마지막 관찰문장을 덜어낸다.
_OBSERVATION_ENDINGS = ("살펴봐 주세요", "살펴봐주세요", "봐 주세요", "봐주세요", "지켜봐 주세요",
                        "지켜봐주세요", "확인해 주세요", "확인해주세요")


def _is_care_method_question(message: str) -> bool:
    t = message or ""
    return any(w in t for w in _CARE_METHOD_WORDS) and any(m in t for m in _CARE_Q_MARKS)


def _is_emotional(message: str) -> bool:
    return any(w in (message or "") for w in _EMOTION_WORDS)


def _ends_with_observation(text: str) -> bool:
    t = (text or "").strip().rstrip(".!?。！？ ")
    return any(t.endswith(e) for e in _OBSERVATION_ENDINGS)


def _is_cancel_execution(message: str) -> bool:
    """'예약 취소해줘/취소할래' 같은 실제 취소 실행 의도. 문의/가정형이면 False."""
    t = message or ""
    if "취소" not in t:
        return False
    if any(m in t for m in _CANCEL_INQUIRY_MARKS):
        return False
    return any(k in t for k in _CANCEL_EXEC_WORDS) or t.strip() in {"예약 취소", "취소"}


def _is_cancel_inquiry(message: str) -> bool:
    """'취소하면 다시 예약돼요?/취소 가능해요?' 같은 정책·가능여부 문의(취소 실행 아님)."""
    t = message or ""
    return "취소" in t and any(m in t for m in _CANCEL_INQUIRY_MARKS)


def _is_affirmative_for_pending(message: str) -> bool:
    text = " ".join((message or "").strip().split())
    return text in _AFFIRMATIVE_SHORTS or (
        len(text) <= 8 and any(k in text for k in ("응", "네", "그래", "좋아")) and not any(
            x in text for x in ("말고", "아니", "취소")
        )
    )


def _patch_pending(action: str = "") -> dict:
    return {"pending_confirmation_action": action}


def _with_pending(result: AgentResult, action: str = "") -> AgentResult:
    result.state_patch = {**(result.state_patch or {}), **_patch_pending(action)}
    return result


def _has_request_ending(text: str) -> bool:
    stripped = (text or "").strip().rstrip(".!?。！？")
    return stripped.endswith(_REQUEST_ENDINGS)


# 답변을 문장 단위로 나눈다(되짚은 앞문장은 살리고 마지막 종결만 교체하기 위함).
_SENTENCE_SPLIT_RE = re.compile(r"[^.!?。！？\n]+(?:[.!?。！？]+|$)")


def _avoid_consecutive_request_ending(reply: str, history: list[dict] | None) -> str:
    """직전 봇 답변도 요청형('알려주세요')으로 끝났으면 같은 종결 반복을 피한다.

    ★ 답변을 통째로 캔드 문장으로 갈아치우지 않는다. 보호자 발화를 되짚은 앞문장은 그대로 두고
    마지막 '요청형 문장'만 다른 종결로 바꿔, 맥락 반영을 잃지 않게 한다.
    """
    if not _has_request_ending(reply):
        return reply
    last = ""
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            last = item.get("content") or ""
            break
    if not _has_request_ending(last):
        return reply
    alt = next((a for a in _ENDING_ALTERNATIVES if a not in last), _ENDING_ALTERNATIVES[0])
    sentences = [m.group(0).strip() for m in _SENTENCE_SPLIT_RE.finditer((reply or "").strip())]
    sentences = [s for s in sentences if s]
    head = sentences[:-1]   # 마지막 요청형 문장만 교체, 되짚은 앞부분은 보존
    if head:
        return " ".join([*head, alt])
    return alt


def _avoid_observation_overload(reply: str, history: list[dict] | None) -> str:
    """관찰 지시('~봐 주세요')가 직전 2턴 연속이었고 이번도 그러면, 체크리스트 반복을 끊는다.

    이번 답변의 마지막 관찰 지시 문장만 덜어내 공감/반영 문장만 남기고, 머리가 없으면 안심 마무리로.
    """
    if not _ends_with_observation(reply):
        return reply
    streak = 0
    for m in reversed(history or []):
        if m.get("role") != "assistant":
            continue
        if _ends_with_observation(m.get("content") or ""):
            streak += 1
            if streak >= 2:
                break
        else:
            break
    if streak < 2:
        return reply
    sentences = [m.group(0).strip() for m in _SENTENCE_SPLIT_RE.finditer((reply or "").strip())]
    sentences = [s for s in sentences if s]
    head = sentences[:-1]
    if head:
        return " ".join(head)
    return "지금은 특별히 더 해주실 건 없어요. 달라지는 모습이 보이면 그때 편하게 알려주세요."


from .schema import (
    Category,
    SeverityHint,
    allows_save_notice_question,
    ensure_safe_reply,
    merge_followup_summary,
    needs_saved_reply_fallback,
    parse_classification,
    strip_save_notice,
)


async def classify_followup(
    ctx: SessionContext,
    user_message: str,
    *,
    vision_findings: str = "",
    vision_relevant: bool | None = None,
    prev_question: str = "",
    last_media_summary: str = "",
):
    """LLM으로 경과 여부 분류. 실패하면 키워드 fallback.

    vision_findings/vision_relevant: 첨부 사진·영상의 VLM 소견(있으면 분류·답변에 반영).
    prev_question: 직전 봇이 던진 질문(있으면 짧은 답변을 그 주제와 연결해 판단하게 한다).
    last_media_summary: 직전 사진 소견(이번 발화가 그 사진을 가리키면 참조하게 한다).
    """
    prompt = build_classification_prompt(
        pet_info=ctx.pet_info,
        followup_summary=ctx.followup_summary,
        history=ctx.history,
        user_message=user_message,
        attachment_count=len(ctx.attachments or []),
        vision_findings=vision_findings,
        vision_relevant=vision_relevant,
        last_reply_kind=ctx.last_followup_reply_kind,
        asked_fields=ctx.asked_followup_fields,
        prev_question=prev_question,
        last_media_summary=last_media_summary,
    )
    try:
        raw = await call_llm_json(prompt)
    except Exception:
        raw = None
    return parse_classification(raw, user_message)


async def analyze_media(ctx: SessionContext, user_message: str) -> tuple[str, bool | None, str]:
    """첨부 이미지/영상을 읽어 (소견, 관련성, 사진속_동물종) 반환. triage vision 재사용(fail-open).

    첨부가 없거나 분석 실패 시 ("", None, "") — 저장/응답 흐름을 막지 않는다.
    species는 등록된 반려동물 종과 대조해 '잘못 보낸 사진'을 가려내는 데 쓴다.
    """
    if not ctx.attachments:
        return "", None, ""
    from ai.agents.triage import vision
    # VLM/다운로드가 가끔 일시적으로 실패해 사진 설명이 빠지는 걸 줄이려고 1회 재시도(fail-open).
    vis = None
    for _ in range(2):
        try:
            vis = await vision.analyze(ctx.attachments, user_message)
        except Exception:
            vis = None
        if vis:
            break
    if not vis:
        return "", None, ""
    findings = (vis.get("note") or "").strip() \
        or ((vis.get("evidence") or {}).get("vlm_description") or "").strip()
    return findings, vis.get("relevant"), (vis.get("species") or "").strip().lower()


def _reply_state_patch(ctx: SessionContext, cls) -> dict:
    """이번 답변의 '목적'과 '물은 항목'을 가벼운 상태로 누적 — 다음 턴 반복 회피용.

    asked_followup_fields는 같은 대화에서 이미 물은 항목을 모아 재질문을 막는다(최근 12개).
    """
    asked = list(dict.fromkeys([*(ctx.asked_followup_fields or []), *cls.asked_fields]))[-12:]
    return {
        "last_followup_reply_kind": cls.reply_kind.value,
        "asked_followup_fields": asked,
    }


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


# 수의사 이름을 못 찾거나 '친절해?/잘 봐?' 같은 주관적 질문일 때 — '정보 없음'으로 끝내지 않는다.
VET_GENERAL_REASSURANCE = "모든 의료진이 반려동물 상태를 꼼꼼히 확인하고 진료하기 위해 노력하고 있어요."


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
        tail = VET_GENERAL_REASSURANCE if subjective else "궁금한 점이 있으면 진료 때 함께 여쭤보면 좋아요."
        return f"이번 예약은 {name}{suffix}이 맡아요. {tail}"
    if subjective:
        return VET_GENERAL_REASSURANCE
    return f"담당 수의사는 예약 내역에서 확인할 수 있어요. {VET_GENERAL_REASSURANCE}"


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


def _quick_replies_for_result(
    result: AgentResult,
    *,
    saved: bool = False,
    emergency: bool = False,
    limited: bool = False,
) -> list[str]:
    if limited:
        return _LIMITED_QUICK_REPLIES
    events = {e.get("type") for e in (result.events or [])}
    if "rebook_request" in events:
        return [SCHEDULE_LIST_PILL, HOSPITAL_INFO_PILL]
    if "list_schedules" in events:
        return [REBOOK_ACTION_PILL, HOSPITAL_INFO_PILL, NEW_BOOKING_DIRECT_PILL]
    if "show_prep" in events:
        return [REBOOK_ACTION_PILL, SCHEDULE_LIST_PILL, HOSPITAL_INFO_PILL]
    if "start_inchat_triage" in events:
        return []
    if result.handoff == Intent.RECEPTION:
        return [SCHEDULE_LIST_PILL, NEW_BOOKING_DIRECT_PILL]
    if saved:
        replies = [CONTINUE_STATUS_PILL, REBOOK_ACTION_PILL]
        if emergency:
            replies.insert(1, REBOOK_PILL)
        return list(dict.fromkeys(replies))
    return result.quick_replies or []


class FollowupFilterAgent:
    name = "followup_filter"
    description = "예약 후 경과 보고를 걸러서, 진짜 경과면 followupDB에 저장하고 잡담이면 넘긴다."

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult:
        user_message = (args or {}).get("user_message") or ctx.user_message or ""
        has_media = bool(ctx.attachments)
        msg = user_message.strip()
        pending_action = (ctx.pending_confirmation_action or "").strip()
        if pending_action and not has_media and _is_affirmative_for_pending(msg):
            return await _run_pending_action(ctx, pending_action)
        if not has_media and msg == CONTINUE_STATUS_PILL:
            return AgentResult(
                reply=FOLLOWUP_LIMITED_REPLY if ctx.followup_limited else "아이 상태에서 달라진 점을 편하게 남겨 주세요.",
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [],
                state_patch=_patch_pending(""),
            )
        if not has_media and msg == HOSPITAL_INFO_PILL:
            return await _run_pending_action(ctx, "hospital_info")
        if not has_media and msg == PREP_INSTRUCTIONS_PILL:
            return await _run_pending_action(ctx, "prep")
        if not has_media and msg == VISIT_NOTE_SUMMARY_PILL:
            return AgentResult(
                reply=_visit_note_summary_reply(ctx),
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [],
                state_patch=_patch_pending(""),
            )

        # P0(맥락 유지): 직전 봇 발화가 '질문'이고 이번이 짧은 긍정/부정/애매 답변이면,
        # 새 요청이 아니라 그 질문에 대한 답으로 보고 clarify 폴백("무엇을 도와드릴까요?")으로 빠지지 않는다.
        prev_question = "" if (has_media or pending_action) else last_assistant_question(ctx.history)
        answering_prev_q = bool(prev_question) and bool(short_answer_kind(msg))

        # P1(사진 기억): 이번 턴 첨부가 없어도 직전 사진을 가리키는 후속 발화면, 최근 사진 소견을 참조한다.
        recent_media = (ctx.last_media_summary or "").strip()
        photo_followup = (not has_media) and bool(recent_media) and is_photo_followup(msg)

        # P3(대화 품질): 관리방법 질문·감정 표현은 clarify로 새지 않게 한다(아래 분기에서 소비).
        is_care_method = (not has_media) and _is_care_method_question(msg)
        is_emotional = (not has_media) and _is_emotional(msg)

        # 사진·영상을 먼저 읽어, 분류·답변·요약에 소견을 반영한다(없으면 빈값).
        vision_findings, vision_relevant, vision_species = await analyze_media(ctx, user_message)
        cls = await classify_followup(
            ctx, user_message,
            vision_findings=vision_findings, vision_relevant=vision_relevant,
            prev_question=prev_question if answering_prev_q else "",
            last_media_summary=recent_media if photo_followup else "",
        )
        # LLM이 그래도 일반 clarify로 답하면(맥락 무시) 무력화 — 저장 경로의 주제연결 fallback이 받게 한다.
        if answering_prev_q and "무엇을 도와드릴까요" in (cls.assistant_reply or ""):
            cls = cls.model_copy(update={"assistant_reply": ""})
        # 사진 후속인데도 '사진이 없다/보내달라'고 하면 무력화 — 직전 소견 기반 fallback이 받게 한다.
        if photo_followup and any(p in (cls.assistant_reply or "") for p in ("사진이 없", "사진을 보내", "사진을 다시")):
            cls = cls.model_copy(update={"assistant_reply": ""})

        # 이번 턴에 '관련 있는' 새 사진을 분석했으면, 다음 턴 후속 발화용으로 짧은 소견을 저장한다(원본 미보관).
        new_media_summary = ""
        if has_media and vision_findings and vision_relevant is not False:
            new_media_summary = vision_findings.strip()[:120]

        is_saved = False

        # 재예약(예약 변경/앞당김) 의도 — LLM 판단 또는 '더 빠른 시간 찾기' pill 클릭.
        # 경과 보고가 아닐 때만 예약 흐름으로 넘긴다(증상 경과는 저장이 우선).
        deterministic_rebook = (
            msg in {REBOOK_PILL, REBOOK_ACTION_PILL}
            or ("예약" in msg and any(k in msg for k in ("바꾸", "변경", "옮기", "당기", "앞당", "빠른", "다른 날")))
        )
        wants_rebook = (cls.wants_rebooking or deterministic_rebook) and not cls.is_followup
        # 예약 취소 — '실행' 의도만 cancel_request. '취소하면 다시 돼요?' 같은 문의/가정형은 제외(이벤트 금지).
        cancel_inquiry = _is_cancel_inquiry(msg)
        deterministic_cancel = _is_cancel_execution(msg) or (
            "예약" in msg and any(k in msg for k in ("안 갈", "못 갈"))
        )
        wants_cancel = (
            ((cls.wants_cancel and not cancel_inquiry) or deterministic_cancel)
            and not cls.is_followup and not wants_rebook
        )

        # 신규(추가) 예약 의도 — '바로 예약 / 문진 작성 후 예약' 선택지를 띄운다(변경=rebook과 구분).
        deterministic_new_booking = (
            msg == NEW_BOOKING_DIRECT_PILL
            or ("예약" in msg and any(k in msg for k in ("새", "새로", "추가", "잡고 싶", "잡을래")))
        )
        wants_new_booking = ((cls.wants_new_booking or deterministic_new_booking) and not cls.is_followup
                             and not wants_rebook and not wants_cancel)
        # '문진 작성 후 예약하기' pill 클릭 → 같은 챗에서 새 문진 시작(start_inchat_triage 이벤트).
        start_inchat_triage = msg == NEW_BOOKING_TRIAGE_PILL
        # 예약 내역 보기 — pill(결정론)은 분류와 무관히 동작, LLM 판단은 경과 아닐 때만.
        asks_schedule_list = (
            msg == SCHEDULE_LIST_PILL
            or msg == "예약 내역 보기"
            or ("예약" in msg and any(k in msg for k in ("내역", "목록", "볼래", "보여")))
            or (cls.asks_schedule_list and not cls.is_followup)
        )
        # 내원 전 준비사항 다시 보기.
        asks_prep = (msg == PREP_INSTRUCTIONS_PILL) or (cls.asks_prep_instructions and not cls.is_followup)

        # 예약 '병원/장소' 질문('어느 병원이야?') → 예약된 병원 정보 안내. 시간 분기보다 우선한다.
        asks_hospital = (
            any(w in user_message for w in _HOSPITAL_LOC_WORDS)
            and not wants_rebook and not wants_cancel and not cls.is_followup
        )
        # '내 예약 시각이 언제인지' 묻는 경우 → 실제 confirmed_time 안내(병원 운영시간 아님).
        # 정확일치 대신 '예약' + (언제/시간/몇시) 부분일치로 견고하게 잡는다(변경 의도는 위에서 제외됨).
        # 단, '어느/무슨/어디 병원·위치·주소'는 시간이 아니라 병원 질문이므로 asks_hospital이 우선.
        asks_time = (
            cls.asks_appointment_time
            or ("예약" in user_message and any(k in user_message for k in ("언제", "시간", "몇 시", "몇시")))
        ) and not asks_hospital and not wants_rebook and not cls.is_followup

        # 병원 인물 질문 → 예약(scheduleDB.doctorid)으로 실제 수의사 이름 안내.
        # 짧은 발화("누구 의사지?")도 예약 컨텍스트와 연결되게 부분일치로 잡는다(병원 행정질문과 별개).
        _msg_has_person = any(k in user_message for k in _VET_PERSON_WORDS)
        asks_vet_factual = cls.asks_vet_info or (
            _msg_has_person and any(k in user_message for k in _VET_FACTUAL_WORDS)
        )
        # "그 의사 친절해?/잘 봐?" 같은 주관 평가 — 단정 대신 따뜻한 일반 안내(유형 4).
        asks_vet_subjective = _msg_has_person and any(k in user_message for k in _VET_SUBJECTIVE_WORDS)
        asks_vet = (asks_vet_factual or asks_vet_subjective) and not wants_rebook and not cls.is_followup

        # 사진 속 동물 종이 등록된 반려동물과 다르면(둘 다 확실할 때만) → 잘못 보낸 사진일 수 있음.
        # ※ 펫 등록 종은 DB에 한글/영어 섞여 있어(예: '고양이') 반드시 정규화해서 비교한다.
        pet_species = canon_species((ctx.pet_info or {}).get("species"))
        photo_species = canon_species(vision_species)
        species_mismatch = (
            has_media and photo_species in _KNOWN_SPECIES
            and pet_species in _KNOWN_SPECIES and photo_species != pet_species
        )

        # 텍스트가 경과도 아닌데 사진이 '무관해 보이면'(relevant=false) → 잘못 보낸 것일 수 있으니
        # 저장하지 말고 한 번 더 확인한다(맞으면 다시 보내달라). 데이터 오염/오알람 방지.
        photo_missent = has_media and (not cls.is_followup) and (vision_relevant is False)
        # 종 불일치는 관련성과 무관하게 '잘못 보낸 사진'으로 본다(강아지 눈병이라도 펫이 고양이면).
        ask_photo = photo_missent or species_mismatch

        if ctx.followup_limited and (wants_rebook or wants_cancel):
            result = AgentResult(reply=BOOKING_CHANGE_LIMITED_REPLY, quick_replies=_LIMITED_QUICK_REPLIES)
        # 0) 재예약 요청 → 저장하지 않고 예약 흐름 신호(rebook_request)를 프론트로 넘긴다.
        elif wants_rebook:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_REBOOK),
                events=[{"type": "rebook_request", "emrid": ctx.emrid}],
            )
        # 0-a) '문진 작성 후 예약하기' → 같은 챗에서 새 문진 시작(백엔드가 new_booking 플래그 ON).
        elif start_inchat_triage:
            result = AgentResult(
                reply=START_TRIAGE_REPLY,
                events=[{"type": "start_inchat_triage", "emrid": ctx.emrid}],
            )
        # 0-b) 신규(추가) 예약 의도 → 바로/문진 선택지를 띄운다(동작은 프론트·후속 턴이 처리).
        elif wants_new_booking:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_NEW_BOOKING_CONFIRM),
                quick_replies=[NEW_BOOKING_DIRECT_PILL, NEW_BOOKING_TRIAGE_PILL],
            )
        # 0-c) 예약 내역 보기 → 현재 예약 목록(show_schedules)을 프론트가 카드로 렌더.
        elif asks_schedule_list:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_SCHEDULE_LIST),
                events=[{"type": "list_schedules", "emrid": ctx.emrid}],
            )
        # 0-d) 내원 전 준비사항 다시 보기 → 저장된 준비사항(show_prep)을 프론트가 카드로 렌더.
        elif asks_prep:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_PREP_INSTRUCTIONS),
                events=[{"type": "show_prep", "emrid": ctx.emrid}],
            )
        # 0-0) 예약 '병원/장소' 질문 → 예약된 병원 정보 안내(시간 아님). reception 핸드오프로 표시.
        elif asks_hospital:
            result = AgentResult(
                reply=await hospital_info_reply(ctx),
                handoff=Intent.RECEPTION,
            )
        # 0-1) '내 예약 시각' 질문 → 실제 confirmed_time 안내(저장 안 함).
        elif asks_time:
            result = AgentResult(reply=await appointment_time_reply(ctx))
        # 0-1b) 병원 인물 질문 → 예약의 실제 수의사 이름 안내(주관 질문이면 일반 안내). 저장 안 함.
        elif asks_vet:
            result = AgentResult(
                reply=await vet_info_reply(ctx, subjective=asks_vet_subjective),
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [HOSPITAL_INFO_PILL, SCHEDULE_LIST_PILL],
            )
        # 0-2a) 취소 '문의/가정형'("취소하면 다시 돼요?") → 취소 이벤트 없이 정책/가능여부만 안내.
        elif cancel_inquiry:
            result = AgentResult(
                reply=(BOOKING_CHANGE_LIMITED_REPLY if ctx.followup_limited else REPLY_CANCEL_POLICY),
                quick_replies=_LIMITED_QUICK_REPLIES if ctx.followup_limited else [SCHEDULE_LIST_PILL, HOSPITAL_INFO_PILL],
            )
        # 0-2) 예약 취소 '실행' 요청 → 저장 안 하고 취소 신호(cancel_request)를 프론트로 넘긴다.
        elif wants_cancel:
            result = AgentResult(
                reply=ensure_safe_reply(cls, REPLY_CANCEL),
                events=[{"type": "cancel_request", "emrid": ctx.emrid}],
            )
        # 1) 저장하지 않는 경우: (경과 아님 + 첨부 없음) 또는 (잘못 보낸 듯한 사진 = 무관/종 불일치).
        #    단, 직전 봇 질문에 대한 짧은 답변(answering_prev_q)이나 직전 사진 후속(photo_followup)이면
        #    clarify로 빠지지 말고 저장 경로로 보내 맥락(질문 주제·사진 소견)을 잇는다.
        elif (not cls.is_followup and not has_media and not answering_prev_q and not photo_followup) or ask_photo:
            if species_mismatch:
                pet_name = (ctx.pet_info or {}).get("name") or "아이"
                result = AgentResult(
                    reply=build_species_mismatch_reply(pet_name, pet_species, photo_species)
                )
            elif photo_missent:
                result = AgentResult(reply=ensure_safe_reply(cls, REPLY_CONFIRM_PHOTO))
            elif cls.category == Category.HOSPITAL_INFO:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_HOSPITAL_INFO),
                    handoff=Intent.RECEPTION,
                )
            # 관리방법 질문 → clarify 금지. LLM의 3부분 답변(care_advice) 우선, 비면 care fallback.
            elif is_care_method or cls.category == Category.PET_GENERAL:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_CARE_METHOD if is_care_method else REPLY_PET_GENERAL),
                    state_patch=_reply_state_patch(ctx, cls),
                )
            # 감정 표현 → 공감 먼저(clarify 금지).
            elif is_emotional:
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_EMOTION_ACK),
                    state_patch=_reply_state_patch(ctx, cls),
                )
            else:
                # 모호/무관 → 차단 멘트 대신 무엇을 원하는지 되묻고, 의도 선택지를 띄운다.
                result = AgentResult(
                    reply=ensure_safe_reply(cls, REPLY_IRRELEVANT),
                    quick_replies=CLARIFY_QUICK_REPLIES,
                )

        elif ctx.followup_limited and (cls.is_followup or has_media):
            result = AgentResult(
                reply=FOLLOWUP_LIMITED_REPLY,
                quick_replies=_LIMITED_QUICK_REPLIES,
                state_patch=_reply_state_patch(ctx, cls),
            )

        else:
            # 2) 저장할 경과 메모(delta) 결정.
            delta = (cls.summary_delta or "").strip()
            if not delta and answering_prev_q:
                # 짧은 답변은 그 자체론 메모가 빈약하므로 직전 질문 주제와 함께 남긴다.
                delta = f"직전 질문 '{prev_question[:30]}'에 '{user_message.strip()}'라고 답함."
            if not delta and photo_followup:
                # 사진 후속도 직전 사진 소견과 함께 남겨 맥락을 보존한다.
                delta = f"직전 사진 소견({recent_media[:60]})에 대해 '{user_message.strip()}'."
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
            # 캔드 멘트는 매번 같은 문장이 반복되지 않게 결정론적으로 변형을 고른다(직전 답변 회피).
            # 사진 후속이면, '사진 없다'가 아니라 직전 사진 소견을 되짚는 fallback을 쓴다.
            if photo_followup:
                fallback_reply = (
                    f"방금 사진에서는 {recent_media.rstrip(' .')}이 보였어요. "
                    "같은 부위가 더 달라지거나 진물이 생기는지 이어서 살펴봐 주세요."
                )
            else:
                fallback_reply = pick_saved_reply(cls.is_followup, ctx.history)
            raw_reply = ensure_safe_reply(cls, fallback_reply)
            allow_save_notice = allows_save_notice_question(user_message)
            reply = strip_save_notice(raw_reply, allow_save_notice=allow_save_notice)
            if needs_saved_reply_fallback(reply, user_message):
                fallback_cls = cls.model_copy(update={"assistant_reply": ""})
                reply = strip_save_notice(
                    ensure_safe_reply(fallback_cls, fallback_reply),
                    allow_save_notice=allow_save_notice,
                )
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
            media_patch = {"last_media_summary": new_media_summary} if new_media_summary else {}
            result = AgentResult(
                reply=reply,
                quick_replies=[],
                state_patch={"followup_summary": updated_summary, **_reply_state_patch(ctx, cls), **media_patch},
                events=events,
            )

        if not result.state_patch.get("pending_confirmation_action"):
            result.state_patch = {**(result.state_patch or {}), **_patch_pending("")}
        if ctx.followup_limited and (wants_rebook or wants_cancel):
            result = _with_pending(result, "")
        elif wants_new_booking:
            result = _with_pending(result, "new_booking")
        elif asks_schedule_list:
            result = _with_pending(result, "schedule_list")
        elif asks_prep:
            result = _with_pending(result, "prep")
        elif asks_time:
            result = _with_pending(result, "appointment_time")
        elif asks_vet:
            result = _with_pending(result, "vet_info")
        elif wants_rebook:
            result = _with_pending(result, "rebook")
        elif result.handoff == Intent.RECEPTION or cls.category == Category.HOSPITAL_INFO:
            result = _with_pending(result, "hospital_info")

        result.reply = _avoid_consecutive_request_ending(result.reply, ctx.history)
        result.reply = _avoid_observation_overload(result.reply, ctx.history)
        result.quick_replies = _quick_replies_for_result(result, saved=is_saved, emergency=(
            cls.severity_hint == SeverityHint.URGENT_POSSIBLE
        ), limited=ctx.followup_limited)

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
