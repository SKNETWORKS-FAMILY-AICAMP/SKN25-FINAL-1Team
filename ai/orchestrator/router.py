"""라우팅 — "이 발화는 누가 답할지" 결정. 담당: 리드. 설계서 §4.

phase로 '후보 에이전트'를 정하고(하드 제약), 그 안에서 누가 답할지는 LLM이 직접 고른다.
  - 예약 전(PRE_BOOKING): reception ⇄ triage  (followup 불가 — 경과는 예약 후에만)
  - 예약 후(BOOKED)     : reception ⇄ followup_filter  (triage 불가 — 재문진 안 함)
라벨→if 매핑이 아니라, 각 에이전트 description을 LLM에 주고 직접 담당을 고르게 한다.
버튼 클릭·예약확정(예/아니오)·첨부 같은 '확정 입력'만 LLM 없이 결정론으로 처리.
"""
from __future__ import annotations

import logging

from ai.llm import call_llm_json

from .contracts import Flow, Phase, SessionContext

logger = logging.getLogger(__name__)

# 후보 에이전트 설명 — 라우터 LLM이 담당을 고를 때 본다. (REGISTRY description 과 동기화)
_AGENT_DESC = {
    "reception": "병원 정보(위치·운영시간·전화·수의사 소개)와 일반 안내. 진단·처방은 수의사께 넘긴다.",
    "triage": "반려동물 증상 문진과 응급도 판정. 증상 호소·문진 답변·되묻기.",
    "followup_filter": "예약 후 경과(증상이 어떻게 바뀌었는지) 보고를 받아 기록한다.",
    "redirect": "반려동물 건강·병원·예약과 무관한 잡담/일반지식 → 정중히 차단.",
}

# 시스템이 직접 제공한 pill — LLM 없이 결정론 처리 (버튼 클릭은 판단이 아니다).
_RECEPTION_PILLS = {"궁금한 게 있어요", "아니요, 괜찮아요", "네, 있어요"}

# LLM 실패 시 폴백용 키워드 — 후보 집합 안에서만 매핑.
_SYMPTOM_KW = ("토", "설사", "아파", "아프", "발작", "경련", "기침", "피", "출혈",
               "절뚝", "절어", "다리", "숨", "호흡", "열", "기력", "안 먹", "구토", "쓰러")
_HOSPITAL_KW = ("병원", "주소", "위치", "어디", "시간", "운영", "전화", "휴진", "몇 시", "몇시",
                "의사", "선생님", "수의사", "원장", "소개", "특징")


def _candidates(ctx: SessionContext) -> list[str]:
    """현재 phase에서 담당 가능한 에이전트 후보(하드 제약 반영)."""
    if ctx.phase == Phase.BOOKED:
        return ["reception", "followup_filter", "redirect"]   # triage 불가(재문진 안 함)
    if ctx.phase == Phase.CLOSED:
        return ["reception", "redirect"]
    return ["reception", "triage", "redirect"]                # 예약 전: followup 불가


def _recent_convo(ctx: SessionContext, n: int = 5) -> str:
    msgs = [m for m in (ctx.history or []) if isinstance(m, dict) and m.get("content")][-n:]
    return "\n".join(f"{m.get('role')}: {m.get('content')}" for m in msgs)


def _fallback(ctx: SessionContext, candidates: list[str]) -> str:
    """LLM 실패 시: 키워드로 후보 안에서만 고른다(결정론 백업)."""
    t = ctx.user_message or ""
    if any(k in t for k in _SYMPTOM_KW):
        if "triage" in candidates:
            return "triage"
        if "followup_filter" in candidates:
            return "followup_filter"
    if any(k in t for k in _HOSPITAL_KW):
        return "reception"
    return "reception"


async def _llm_pick(ctx: SessionContext, candidates: list[str]) -> str:
    """후보 에이전트 설명을 주고, 이번 발화의 담당을 LLM이 직접 고르게 한다."""
    desc = "\n".join(f"- {n}: {_AGENT_DESC[n]}" for n in candidates if n in _AGENT_DESC)

    if ctx.phase == Phase.BOOKED:
        phase_hint = ("지금은 '예약 후'야. 증상 변화·경과 보고는 followup_filter, "
                      "병원 정보·일반 안내는 reception. (증상 문진은 더 안 한다)")
    elif ctx.phase == Phase.CLOSED:
        phase_hint = "지금은 입력 마감 상태야. 병원 안내(reception)만 가능."
    else:
        phase_hint = ("지금은 '예약 전'이야. 증상 문진·증상 호소는 triage, "
                      "병원 정보·일반 안내는 reception.")
        if ctx.emrid is not None:
            phase_hint += " 문진은 이미 완료됨(재문진하지 말 것)."

    if ctx.active_flow == Flow.TRIAGING:
        phase_hint += (" 지금 증상 문진이 진행 중이야 — 직전 봇 질문의 답·증상·되묻기·잡담이면 "
                       "triage로 이어가고, 분명히 병원 정보로 화제를 바꿀 때만 reception.")

    prompt = (
        "동물병원 챗봇의 라우터야. 아래 보호자 발화를 '누가' 처리해야 할지 후보 중 하나의 이름만 골라.\n"
        f"{phase_hint}\n\n[후보 에이전트]\n{desc}\n\n"
        f"[최근 대화]\n{_recent_convo(ctx)}\n[이번 발화] {ctx.user_message}\n\n"
        'JSON으로만: {"agent": "후보 이름 중 하나"}'
    )
    try:
        out = await call_llm_json(prompt)
        pick = (out.get("agent") or "").strip()
        if pick in candidates:
            return pick
        logger.warning("[router] LLM이 후보 밖 선택(%r), 폴백", pick)
    except Exception as e:
        logger.warning("[router] LLM 담당 선택 실패, 폴백: %s", e)
    return _fallback(ctx, candidates)


async def route(ctx: SessionContext) -> str:
    """반환: 처리 노드 이름 {reception|triage|schedule|followup_filter|redirect}."""
    # 0) 시스템 pill 텍스트 — 결정론 (버튼 클릭은 판단 아님)
    if ctx.user_message in _RECEPTION_PILLS:
        return "reception"

    # 1) 예약확인(예/아니오) 대기 = 짧은 결정 게이트 → 결정론적으로 triage가 받는다.
    if ctx.active_flow == Flow.AWAITING_BOOKING_CONFIRM:
        return "triage"

    # 2) 슬롯 고르는 중 = 예약 플로우 잠금 → 결정론적으로 schedule.
    if ctx.active_flow == Flow.SCHEDULING:
        return "schedule"

    # 3) 첨부(사진/영상)는 증상/경과 신호 — phase에 따라 담당 고정.
    if ctx.attachments:
        if ctx.phase == Phase.BOOKED:
            return "followup_filter"
        if ctx.phase == Phase.PRE_BOOKING:
            return "triage"
        return "reception"

    # 4) 예약 후(BOOKED) 발화는 followup_filter가 통합 처리.
    #    - 실제 경과 → DB 저장 + 모니터링 로그 Y
    #    - 무관 발화(잡담·병원정보 등) → 모니터링 로그 N (is_saved=false)
    #    followup_filter 내부에서 분류 후 HOSPITAL_INFO면 reception handoff 처리.
    if ctx.phase == Phase.BOOKED:
        return "followup_filter"

    # 5) phase로 후보를 정하고(하드 제약), 그 안에서 LLM이 직접 담당을 고른다.
    return await _llm_pick(ctx, _candidates(ctx))
