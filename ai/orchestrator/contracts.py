"""오케스트레이터 v2 공용 계약 — 모든 에이전트가 이 입출력 규격을 따른다.

★ Day1에 팀과 공유하는 '단일 기준' 파일. 이게 확정돼야 A·B·C가 병렬로 일한다.
설계서 §10 참고.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Phase(str, Enum):
    """대화 국면 — 후보 에이전트를 결정한다."""
    PRE_BOOKING = "PRE_BOOKING"   # 예약 전: 응대 + 문진 + 예약
    BOOKED = "BOOKED"             # 예약 후: 응대 + 경과필터
    CLOSED = "CLOSED"             # 예약 시각 지남: 입력 마감


class Flow(str, Enum):
    """지금 무슨 흐름 한복판인가 — sticky 라우팅에 쓰인다."""
    IDLE = "idle"
    TRIAGING = "triaging"         # 문진 진행 중 (끼어들어도 여기로 복귀)
    SCHEDULING = "scheduling"     # 슬롯 고르는 중


class Intent(str, Enum):
    """라우터가 한 턴을 보낼 곳."""
    RECEPTION = "reception"               # 병원 정보 응대
    TRIAGE = "triage"                     # 증상 문진
    SCHEDULE = "schedule"                 # 예약 시간 추천
    FOLLOWUP_FILTER = "followup_filter"   # 예약 후 경과 필터
    PET_GENERAL = "pet_general"           # "비타민 먹여도 돼?" → 응대 가드레일로 처리
    UNRELATED = "unrelated"               # "파이썬" 등 → 정중히 차단


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
    scheduleid: int | None                # scheduleDB (예약 확정 시)
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
    # --- 런타임 핸들 (저장 안 함) ---
    db: Any = None
    session: Any = None       # chat_historyDB ORM row (DB 적재용)


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
