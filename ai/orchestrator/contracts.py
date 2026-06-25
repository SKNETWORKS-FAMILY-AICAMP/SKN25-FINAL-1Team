"""오케스트레이터 v2 공용 계약 — 모든 에이전트가 이 입출력 규격을 따른다.

★ Day1에 팀과 공유하는 '단일 기준' 파일. 이게 확정돼야 A·B·C가 병렬로 일한다.
설계서 §10 참고.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

# 채팅 시작 시 노출되는 '문진 시작' 진입 pill — chat.py/router/triage가 공유하는 단일 출처.
INITIAL_TRIAGE_PILL = "증상을 말하고 예약할래요"

# 문진 중 비증상 응대(메타·잡담 등) 뒤 띄우는 '여기서 마칠게요' 종료 pill — 단일 출처.
# 글자가 'OO 괜찮아요?'의 증상 답과 안 겹치게 명확한 종료어로 둔다(router/triage가 결정론 처리).
TRIAGE_CLOSE_PILL = "아니요, 괜찮아요"

# 문진 시작 직후 보호자가 증상 범주를 빠르게 고를 수 있게 노출하는 기본 pill.
INITIAL_SYMPTOM_PILLS = [
    "구토",
    "설사",
    "피부",
    "기침",
    "식욕저하",
    "눈물",
    "절뚝거림",
]


class Phase(str, Enum):
    """대화 국면 — 후보 에이전트를 결정한다.

    실제로 산출되는 값은 PRE_BOOKING / BOOKED 둘뿐이다(state._compute_phase 참고).
    과거 예약도 채팅방을 닫지 않고 BOOKED로 다루므로 별도 종료 국면은 두지 않는다.
    """
    PRE_BOOKING = "PRE_BOOKING"   # 예약 전: 응대 + 문진 + 예약
    BOOKED = "BOOKED"             # 예약 후(과거 예약 포함): 응대 + 경과필터


class Flow(str, Enum):
    """지금 무슨 흐름 한복판인가 — sticky 라우팅에 쓰인다."""
    IDLE = "idle"
    TRIAGING = "triaging"         # 문진 진행 중 (끼어들어도 여기로 복귀)
    SCHEDULING = "scheduling"     # 슬롯 고르는 중
    AWAITING_BOOKING_CONFIRM = "awaiting_booking_confirm"  # 의심질환 안내 후 예약 여부(예/아니오) 대기


class Intent(str, Enum):
    """에이전트가 '다음 턴을 누구에게 넘길지' 알리는 handoff 힌트(AgentResult.handoff).

    라우팅 자체는 Intent가 아니라 노드 이름 문자열로 동작한다(router.route 반환값).
    실제로 쓰이는 handoff 값은 RECEPTION 하나뿐이라 그것만 둔다.
    """
    RECEPTION = "reception"               # 병원 정보 응대로 넘김


@dataclass
class SessionContext:
    """지휘자가 매 턴 DB에서 만들어 각 에이전트에 넘기는 '현재 상황 묶음'."""
    # --- 식별 / 원천: chat_historyDB row + 관련 테이블 ---
    session_id: int                       # chat_historyDB.id
    userid: int                           # chat_historyDB.userid
    petid: int                            # chat_historyDB.petid
    pet_info: dict                        # petDB (이름/종/품종/나이/체중/성별)
    hospitalid: int | None                # guardian_hospitalDB.is_primary
    emrid: int | None                     # chat_historyDB.emrid (문진 완료 시 발급)
    scheduleid: int | None                # 현재 예약(scheduleDB.scheduleid) — BOOKED일 때 채워짐
    # --- 이번 턴 대화 ---
    user_message: str                     # 이번 턴 사용자 발화
    attachments: list[str] = field(default_factory=list)  # 첨부 이미지/영상 URL
    history: list[dict] = field(default_factory=list)     # chat_historyDB.messages (최근 N개)
    # --- 오케스트레이터 상태: chat_historyDB.orch_state(JSON, 신규 컬럼)에 저장 ---
    phase: Phase = Phase.PRE_BOOKING
    active_flow: Flow = Flow.IDLE
    reception_streak: int = 0             # 응대 연속 횟수(넛지 트리거)
    triage_state: dict = field(default_factory=dict)   # 문진 슬롯/물은질문/횟수
    followup_summary: str = ""            # 누적 경과 메모
    # followup 답변 다양화(반복 회피)용 가벼운 상태 — 직전 답변 목적 + 같은 대화에서 이미 물은 항목.
    last_followup_reply_kind: str = ""
    asked_followup_fields: list[str] = field(default_factory=list)
    pending_confirmation_action: str = ""
    # 직전(최근 1개) 사진/영상 분석 소견 요약 — 다음 턴의 '사진 후속' 발화에서 참조한다(원본 미보관).
    last_media_summary: str = ""
    # 채팅 에이전트 공통 durable 맥락 — 직전 문진 결론(주증상·요약)을 reception/followup이 잇도록
    # 오케스트레이터가 주입한다(읽기 전용 조합값, 저장 안 함). conversation.triage_context() 산출.
    conversation_memory: str = ""
    followup_limited: bool = False
    # 예약 후(BOOKED) 챗에서 '문진 작성 후 새로 예약하기'를 고른 경우 — 같은 세션에서 새 문진을
    # 돌리도록 phase를 PRE_BOOKING으로 강등하고, 문진 완료 시 새 emrid를 발급한다(완료 시 해제).
    new_booking: bool = False
    # --- 런타임 핸들 (저장 안 함) ---
    db: Any = None
    session: Any = None       # chat_historyDB ORM row (DB 적재용)
    status_queue: Any = None  # 진행 상태(예: 증상 검색중) SSE 푸시용 asyncio.Queue (없을 수 있음)


@dataclass
class AgentResult:
    """모든 에이전트가 똑같이 이 모양으로 답을 돌려준다."""
    reply: str = ""                       # 보호자에게 보일 답
    quick_replies: list[str] = field(default_factory=list)   # 버튼(pill)
    state_patch: dict = field(default_factory=dict)          # orch_state에 머지할 변경분
    events: list[dict] = field(default_factory=list)         # 추가 SSE 신호(예약완료 등)
    handoff: Intent | None = None         # "다음 턴은 예약으로" 같은 넘김 힌트


class AgentNode(Protocol):
    """각 에이전트는 이 규격을 만족하는 객체. (LangGraph 노드로 감싼다)"""
    name: str
    description: str   # 라우터 LLM에게 주는 설명

    async def run(self, ctx: SessionContext, args: dict) -> AgentResult: ...
