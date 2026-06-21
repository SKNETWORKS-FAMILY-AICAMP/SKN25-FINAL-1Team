"""라우팅 — "이 발화는 누가 답할지" 결정. 담당: 리드.
설계서 §4 / AGENT_SPECS '공통 동작 규칙'. 규칙 먼저(결정론) → LLM 분류.
"""
from __future__ import annotations

import logging

from ai.llm import call_llm_json

from .contracts import Flow, Phase, SessionContext

logger = logging.getLogger(__name__)

# 분류기에 주는 지시문 — 발화를 한 라벨로 분류
_CLASSIFY_PROMPT = """다음 보호자 발화를 한 단어 라벨로만 분류해.
- hospital : 병원 위치·주소·운영시간·휴진일·전화·수의사(의료진) 소개·병원 특징 등 '병원 정보' 질문
- symptom  : 반려동물 증상·상태 호소(예: 토해요, 다리를 절어요, 발작했어요, 기침, 발작, 피부, 기타)
- booking  : 예약하고 싶다는 의사(예: 예약하기, 예약할게요, 건강검진)
- care     : 반려동물 일반질문(예: 비타민 먹여도 돼?, 사료 추천, 괜찮아요)
- followup : 예약 후 경과 보고(증상이 어떻게 바뀌었는지)
- other    : 위와 무관(잡담, 일반지식 등)

JSON으로만: {"label": "symptom"}"""

# LLM 실패 시 쓰는 아주 단순한 키워드 백업
_SYMPTOM_KW = ("토", "설사", "아파", "아프", "발작", "경련", "기침", "피", "출혈",
               "절뚝", "절어", "다리", "숨", "호흡", "열", "기력", "안 먹", "구토", "쓰러")
_HOSPITAL_KW = ("병원", "주소", "위치", "어디", "시간", "운영", "전화", "휴진", "몇 시", "몇시",
                "의사", "선생님", "수의사", "원장", "소개", "특징")
_BOOKING_KW = ("예약",)

# 시스템이 직접 제공한 pill 텍스트 — LLM 분류 없이 결정론적으로 처리
_RECEPTION_PILLS = {"궁금한 게 있어요", "아니요, 괜찮아요", "네, 있어요"}


def _heuristic(text: str) -> str:
    t = text or ""
    if any(k in t for k in _BOOKING_KW):
        return "booking"
    if any(k in t for k in _SYMPTOM_KW):
        return "symptom"
    if any(k in t for k in _HOSPITAL_KW):
        return "hospital"
    return "care"


def _recent_convo(ctx: SessionContext, n: int = 5) -> str:
    msgs = [m for m in (ctx.history or []) if isinstance(m, dict) and m.get("content")][-n:]
    return "\n".join(f"{m.get('role')}: {m.get('content')}" for m in msgs)


async def _classify(text: str, ctx: SessionContext | None = None) -> str:
    """발화 분류 — '맨몸 발화'가 아니라 '최근 대화 맥락'까지 보고 라벨을 고른다.
    문진 중엔 직전 질문의 답·증상·잡담을 hospital로 오인하지 않게 강하게 편향시킨다."""
    flow_hint = ""
    if ctx is not None and ctx.active_flow == Flow.TRIAGING:
        flow_hint = ("\n[지금 상황] 보호자는 '증상 문진' 중이다. 직전 봇 질문에 대한 답이거나 "
                     "증상·걱정·되묻기·잡담이면 'symptom'으로 본다. "
                     "'hospital'은 보호자가 분명히 병원 운영시간·위치·전화·휴진 같은 '병원 정보'로 "
                     "화제를 바꿀 때만 골라라(증상 얘기 중 병원을 스쳐 언급한 정도면 symptom).")
    convo = _recent_convo(ctx) if ctx is not None else ""
    prompt = (f"{_CLASSIFY_PROMPT}{flow_hint}\n\n"
              f"[최근 대화]\n{convo}\n[분류할 발화] {text}")
    try:
        out = await call_llm_json(prompt)
        label = (out.get("label") or "").strip().lower()
        if label in {"hospital", "symptom", "booking", "care", "followup", "other"}:
            return label
    except Exception as e:
        logger.warning("[router] LLM 분류 실패, 휴리스틱 사용: %s", e)
    return _heuristic(text)


async def route(ctx: SessionContext) -> str:
    """반환: 처리 노드 이름 {reception|triage|schedule|followup_filter|redirect}."""
    # 0) 시스템 pill 텍스트 — 결정론적으로 처리 (LLM 호출 없음)
    if ctx.user_message in _RECEPTION_PILLS:
        return "reception"

    # 1) 예약확인(예/아니오) 대기 = 짧은 결정 게이트라 결정론적으로 triage가 받는다.
    #    (여기서 LLM 라우팅을 돌리면 "예"가 엉뚱하게 분류될 수 있어 의도적으로 고정)
    if ctx.active_flow == Flow.AWAITING_BOOKING_CONFIRM:
        return "triage"

    # 2) LLM 분류(맥락 인식) — 사진/영상 첨부는 '증상 신호'로 간주.
    label = "symptom" if ctx.attachments else await _classify(ctx.user_message, ctx)

    # 2.5) 동적 라우팅(문진 중) — 매 턴 LLM이 화제를 보고 에이전트를 고른다.
    #   기본은 triage가 이어받되(증상답·되묻기·잡담·종료는 triage가 내부에서 응대),
    #   '명확한 병원 정보'로 화제를 바꾸면 그 턴만 응대로 우회 → 응대는 active_flow를 안 건드리므로
    #   다음 증상 발화에서 문진이 자동 복귀(turn_count·수집정보 그대로 보존).
    if ctx.active_flow == Flow.TRIAGING:
        return "reception" if label == "hospital" else "triage"

    # 3) phase별 매핑
    if ctx.phase == Phase.BOOKED:
        if label == "hospital":
            return "reception"
        if label in ("symptom", "followup", "booking"):
            return "followup_filter"   # 예약 후 = 경과로 수집
        if label == "care":
            return "reception"
        return "redirect"

    if ctx.phase == Phase.CLOSED:
        return "reception" if label == "hospital" else "redirect"

    # PRE_BOOKING
    if ctx.active_flow == Flow.SCHEDULING and label in ("booking", "symptom"):
        return "schedule"            # 문진 끝나고 시간 고르는 중
    # 문진 완료(emrid 발급) 후: 같은 세션에선 재문진하지 않는다(응급도→예약 한 플로우).
    #  - 'booking'(다시 예약) → triage가 재문진 없이 예약 재개(저장된 기록으로)
    #  - 'symptom'(증상 재발화) → 새 문진 안 하고 가볍게 응대
    if ctx.emrid is not None:
        if label == "booking":
            return "triage"
        if label == "symptom":
            return "reception"
    if label in ("symptom", "booking"):
        return "triage"              # 증상·예약 → 문진부터 (예약은 문진 경유)
    if label in ("hospital", "care"):
        return "reception"           # care는 응대의 가드레일이 처리
    return "redirect"                # other
