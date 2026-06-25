"""경과 필터 응답 정책 — quick_replies 선택, pending/state 패치, 반복 톤 완화.

agent.py에서 '동작 변경 없이' 분리한 순수 헬퍼 모음(말단 모듈: 다른 followup_filter
모듈에 의존하지 않는다). 분기 로직·문구·이벤트는 일절 바꾸지 않았다.
"""
from __future__ import annotations

import re

from ai.orchestrator.contracts import AgentResult, Intent, SessionContext

from .prompts import (
    CONTINUE_STATUS_PILL,
    HOSPITAL_INFO_PILL,
    NEW_BOOKING_DIRECT_PILL,
    PREP_INSTRUCTIONS_PILL,
    REBOOK_ACTION_PILL,
    REBOOK_PILL,
    SCHEDULE_LIST_PILL,
    VISIT_NOTE_SUMMARY_PILL,
)

_REQUEST_ENDINGS = ("알려주세요", "함께 알려주세요", "말씀해 주세요", "말씀해주세요")
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
# 반복 관찰안내 종결 — 3턴 연속이면 마지막 관찰문장을 덜어낸다.
_OBSERVATION_ENDINGS = ("살펴봐 주세요", "살펴봐주세요", "봐 주세요", "봐주세요", "지켜봐 주세요",
                        "지켜봐주세요", "확인해 주세요", "확인해주세요")

# 답변을 문장 단위로 나눈다(되짚은 앞문장은 살리고 마지막 종결만 교체하기 위함).
_SENTENCE_SPLIT_RE = re.compile(r"[^.!?。！？\n]+(?:[.!?。！？]+|$)")


def _ends_with_observation(text: str) -> bool:
    t = (text or "").strip().rstrip(".!?。！？ ")
    return any(t.endswith(e) for e in _OBSERVATION_ENDINGS)


def _has_request_ending(text: str) -> bool:
    stripped = (text or "").strip().rstrip(".!?。！？")
    return stripped.endswith(_REQUEST_ENDINGS)


def _patch_pending(action: str = "") -> dict:
    return {"pending_confirmation_action": action}


def _reply_state_patch(ctx: SessionContext, cls) -> dict:
    """이번 답변의 '목적'과 '물은 항목'을 가벼운 상태로 누적 — 다음 턴 반복 회피용.

    asked_followup_fields는 같은 대화에서 이미 물은 항목을 모아 재질문을 막는다(최근 12개).
    """
    asked = list(dict.fromkeys([*(ctx.asked_followup_fields or []), *cls.asked_fields]))[-12:]
    return {
        "last_followup_reply_kind": cls.reply_kind.value,
        "asked_followup_fields": asked,
    }


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
        if emergency:
            # 응급 경과: 다음 행동을 바로 할 수 있게 '더 빠른 시간 찾기'를 맨 앞에 둔다.
            replies = [REBOOK_PILL, CONTINUE_STATUS_PILL, REBOOK_ACTION_PILL]
        else:
            replies = [CONTINUE_STATUS_PILL, REBOOK_ACTION_PILL]
        return list(dict.fromkeys(replies))
    return result.quick_replies or []


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
