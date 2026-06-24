"""라우팅 — "이 발화는 누가 답할지" 결정. 담당: 리드. 설계서 §4.

phase로 '후보 에이전트'를 정하고(하드 제약), 그 안에서 누가 답할지는 LLM이 직접 고른다.
  - 예약 전(PRE_BOOKING): reception ⇄ triage  (followup 불가 — 경과는 예약 후에만)
  - 예약 후(BOOKED)     : reception ⇄ followup_filter  (triage 불가 — 재문진 안 함)
라벨→if 매핑이 아니라, 각 에이전트 description을 LLM에 주고 직접 담당을 고르게 한다.
버튼 클릭·예약확정(예/아니오)·첨부 같은 '확정 입력'만 LLM 없이 결정론으로 처리.
"""
from __future__ import annotations

import logging

from langfuse import observe

from ai.llm import call_llm_json

from .contracts import INITIAL_TRIAGE_PILL, TRIAGE_CLOSE_PILL, Flow, Phase, SessionContext
from .registry import REGISTRY

logger = logging.getLogger(__name__)

# 후보 에이전트 설명 — 라우터 LLM이 담당을 고를 때 본다.
# 단일 출처: 각 에이전트의 .description 을 그대로 읽어 라우터-에이전트 설명 드리프트를 없앤다.
# redirect 는 REGISTRY에 없는 그래프 전용 노드라 여기서만 설명을 단다.
_AGENT_DESC = {name: agent.description for name, agent in REGISTRY.items()}
_AGENT_DESC["redirect"] = "반려동물 건강·병원·예약과 무관한 잡담/일반지식 → 정중히 차단."

# 시스템이 직접 제공한 pill — LLM 없이 결정론 처리 (버튼 클릭은 판단이 아니다).
_RECEPTION_PILLS = {"궁금한 게 있어요", "아니요, 괜찮아요", "네, 있어요"}
# 초기 진입 pill — '증상 말하고 예약' → 무조건 문진으로 (예약 글자에 휘둘려 reception으로 새지 않게).
_TRIAGE_PILLS = {INITIAL_TRIAGE_PILL}

# LLM 실패 시 폴백용 키워드 — 후보 집합 안에서만 매핑.
_SYMPTOM_KW = ("토", "설사", "아파", "아프", "발작", "경련", "기침", "피", "출혈",
               "절뚝", "절어", "다리", "숨", "호흡", "열", "기력", "안 먹", "구토", "쓰러")
_HOSPITAL_KW = ("병원", "주소", "위치", "어디", "시간", "운영", "전화", "휴진", "몇 시", "몇시",
                "의사", "선생님", "수의사", "원장", "소개", "특징")
_CARE_KW = ("비타민", "영양제", "보충제", "사료", "간식", "추천", "먹여도", "급여",
            "케어", "관리", "목욕", "양치", "빗질", "미용", "산책")
_AFFIRMATIVE_KW = ("확인", "응", "네", "그래", "보여", "해줘", "해 줘", "좋아")


def _candidates(ctx: SessionContext) -> list[str]:
    """현재 phase에서 담당 가능한 에이전트 후보(하드 제약 반영)."""
    if ctx.phase == Phase.BOOKED:
        # 예약 후 자연스러운 후속 질문(사진 못 찍음·상태 얘기 등)을 redirect로 차단하지 않고
        # followup_filter가 받아 되묻게 한다. 병원 정보(위치/시간/전화)만 reception.
        return ["reception", "followup_filter"]   # triage·redirect 불가

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
    if any(k in t for k in _CARE_KW):
        return "reception"
    if "followup_filter" in candidates:
        return "followup_filter"
    return "reception"


async def _llm_pick(ctx: SessionContext, candidates: list[str]) -> str:
    """후보 에이전트 설명을 주고, 이번 발화의 담당을 LLM이 직접 고르게 한다."""
    desc = "\n".join(f"- {n}: {_AGENT_DESC[n]}" for n in candidates if n in _AGENT_DESC)

    if ctx.phase == Phase.BOOKED:
        # 예약 후엔: 아이 상태 관련 모든 대화·질문 + 예약 변경/재예약 + '내 예약 시각 확인'은
        # followup_filter가 받아 챗 안에서 처리한다(홈으로 떠넘기지 않음).
        # reception은 '병원 위치·운영시간·전화·수의사 소개' 같은 순수 병원 정보만.
        phase_hint = ("지금은 '예약 후'야. 아이 상태 관련 대화·질문, 예약 변경·재예약, "
                      "'내 예약 시각이 언제인지' 확인은 모두 followup_filter. "
                      "병원 위치·운영시간·전화 같은 순수 병원 정보만 reception. (증상 문진은 더 안 한다)")
    else:
        phase_hint = ("지금은 '예약 전'이야. 증상 문진·증상 호소는 triage, "
                      "병원 정보·비타민·영양제·사료·간식 추천 같은 일반 케어 질문은 reception. "
                      "예약은 문진을 거쳐야 가능하므로, 증상 설명 없이 '바로 예약'만 원하는 발화도 "
                      "reception이 아니라 triage가 받아서 안내한다.")
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


@observe(name="router")
async def route(ctx: SessionContext) -> str:
    """반환: 처리 노드 이름 {reception|triage|schedule|followup_filter|redirect}."""
    # 0) 시스템 pill 텍스트 — 결정론 (버튼 클릭은 판단 아님)
    # 문진 중 띄운 '아니요, 괜찮아요'(종료 pill)는 같은 글자가 reception 종료 pill과 겹치므로
    # 문진 진행 중일 때만 triage로 보내 결정론 종료시킨다(reception으로 새 증상 캐묻기 방지).
    if ctx.active_flow == Flow.TRIAGING and ctx.user_message == TRIAGE_CLOSE_PILL:
        return "triage"
    if ctx.user_message in _RECEPTION_PILLS:
        return "reception"
    if ctx.user_message in _TRIAGE_PILLS:
        return "triage"

    # 1) 예약확인(예/아니오) 대기 = 짧은 결정 게이트 → 결정론적으로 triage가 받는다.
    if ctx.active_flow == Flow.AWAITING_BOOKING_CONFIRM:
        return "triage"

    # 2) 슬롯 고르는 중 = 예약 플로우 잠금 → 결정론적으로 schedule.
    if ctx.active_flow == Flow.SCHEDULING:
        return "schedule"

    if ctx.phase == Phase.BOOKED and ctx.pending_confirmation_action:
        text = (ctx.user_message or "").strip()
        if len(text) <= 12 and any(k in text for k in _AFFIRMATIVE_KW):
            return "followup_filter"

    # 3) 첨부(사진/영상)는 증상/경과 신호 — phase에 따라 담당 고정.
    if ctx.attachments:
        if ctx.phase == Phase.BOOKED:
            return "followup_filter"
        if ctx.phase == Phase.PRE_BOOKING:
            return "triage"
        return "reception"

    # (예전엔 PRE_BOOKING + CARE_KW면 무조건 reception으로 단락시켰는데, "산책하면 내려가나요?"처럼
    #  증상·응급 발화가 케어 단어를 품으면 triage(+안전 선별)를 건너뛰는 오라우팅이 났다. 케어 vs 증상
    #  판단은 LLM 라우터에 맡긴다 — phase_hint가 이미 '케어 질문은 reception'을 안내한다.)

    if ctx.phase == Phase.BOOKED:
        text = ctx.user_message or ""
        if "예약" in text and any(k in text for k in ("병원", "시간", "시각", "몇 시", "몇시", "내역", "목록")):
            return "followup_filter"

    # 4) phase로 후보를 정하고(하드 제약), 그 안에서 LLM이 직접 담당을 고른다.
    picked = await _llm_pick(ctx, _candidates(ctx))

    # BOOKED 상태에서 followup_filter가 아닌 에이전트로 가면 "저장 안 됨(N)" 로그 기록
    # emrid가 없으면 eval 테스트 컨텍스트이므로 로그 생략
    if ctx.phase == Phase.BOOKED and picked != "followup_filter" and ctx.emrid is not None:
        from ai.monitoring import push_log
        _CATEGORY_MAP = {"reception": "병원안내", "redirect": "무관발화"}
        push_log("followup_filter", {
            "emrid": ctx.emrid,
            "scheduleid": ctx.scheduleid,
            "message": (ctx.user_message or "")[:80],
            "category": _CATEGORY_MAP.get(picked, picked),
            "severity": "none",
            "is_saved": False,
            "has_media": bool(ctx.attachments),
        })

    return picked
