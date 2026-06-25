"""경과 필터 LLM 출력 스키마 + 안전 파싱/머지 유틸.  담당: B

- LLM은 JSON만 뱉게 시키고, 여기서 Pydantic으로 검증한다.
- enum이 틀리거나 JSON 파싱이 깨지면 키워드 기반으로 보수적으로 분류(fallback).
- followup_summary 누적 머지도 코드에서 결정론적으로 처리.
"""
from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    SYMPTOM_CHANGE = "symptom_change"
    MEDICATION_RESPONSE = "medication_response"
    APPETITE_ENERGY = "appetite_energy"
    STOOL_URINE = "stool_urine"
    PAIN_BEHAVIOR = "pain_behavior"
    HOSPITAL_INFO = "hospital_info"
    PET_GENERAL = "pet_general"
    IRRELEVANT = "irrelevant"
    OTHER = "other"


class SeverityHint(str, Enum):
    STABLE = "stable"            # 호전·유지·가벼운 변화
    WORSE = "worse"              # 악화 가능성
    URGENT_POSSIBLE = "urgent_possible"  # 즉시 병원 연락 안내 가능성


class ReplyKind(str, Enum):
    """이번 답변의 '목적' — 매 답변이 정확히 하나만 갖는다(직전과 다른 목적을 권장)."""
    REFLECT_ASK = "reflect_ask"              # 변화 반영 + 필요한 정보 1개 질문
    STABLE_NEXT = "stable_next"              # 호전/안정 확인 + 다음 관찰 포인트 1개
    URGENT_REBOOK = "urgent_rebook"          # urgent일 때만 — 더 빠른 예약 안내
    GENERAL_DISCHARGE = "general_discharge"  # 일반 질문 — 퇴원안내 우선 + 현재 상태 1개 질문
    CARE_ADVICE = "care_advice"              # 관리방법 질문 — 무리 말 것 + 확인 포인트 + 진료 시 전달
    EMPATHY = "empathy"                      # 감정 표현 — 공감 먼저, 단정 없이 안심
    REASSURE_CLOSE = "reassure_close"        # 여러 정상 확인됨 — 체크리스트 멈추고 안심하며 마무리
    OTHER = "other"


# 경과(수의사 전달 대상)로 보는 카테고리
FOLLOWUP_CATEGORIES = {
    Category.SYMPTOM_CHANGE,
    Category.MEDICATION_RESPONSE,
    Category.APPETITE_ENERGY,
    Category.STOOL_URINE,
    Category.PAIN_BEHAVIOR,
}


class FollowupClassification(BaseModel):
    """LLM이 채우는 경과 분류 결과.

    summary_delta: DB(ai_summary)용 — 짧고 구조적인 의료 메모.
    assistant_reply: 보호자가 실제로 읽는 자연스러운 답변.
    confidence: 분류 확신도 0.0~1.0 (평가·모니터링용).
    """
    is_followup: bool = False
    category: Category = Category.OTHER
    severity_hint: SeverityHint = SeverityHint.STABLE
    summary_delta: str = ""
    assistant_reply: str = ""
    # 이번 답변의 목적(직전과 다르게) + 이번에 물은 항목(같은 대화 재질문 회피용).
    reply_kind: ReplyKind = ReplyKind.OTHER
    asked_fields: list[str] = Field(default_factory=list)
    reason: str = ""
    # 보호자가 '예약 시간 변경/재예약'을 원하면 true (증상 경과와 별개 — 예약 흐름으로 넘긴다).
    wants_rebooking: bool = False
    # 보호자가 '내 예약이 언제인지(예약 시각)'를 물으면 true → 실제 confirmed_time을 안내.
    asks_appointment_time: bool = False
    # 보호자가 '예약 취소'를 원하면 true → 프론트에서 확인 후 예약 취소.
    wants_cancel: bool = False
    # 보호자가 '새로(추가로) 예약을 잡고 싶다'(기존 예약 변경이 아니라 신규)면 true →
    # 챗에서 '바로 예약 / 문진 작성 후 예약' 선택지를 띄운다. (변경=wants_rebooking과 구분)
    wants_new_booking: bool = False
    # 보호자가 '내 예약 내역/기록을 보여달라'고 하면 true → 현재 예약 목록 카드 + 예약내역 탭 안내.
    asks_schedule_list: bool = False
    # 보호자가 '내원 전 준비사항을 다시 알려달라'고 하면 true → 저장된 준비사항을 다시 보여준다.
    asks_prep_instructions: bool = False
    # 보호자가 '이번 예약 담당 수의사가 누구인지' 물으면 true → scheduleDB.doctorid로 실제 이름 안내.
    asks_vet_info: bool = False
    confidence: float = 0.5

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        try:
            f = float(v)
            return max(0.0, min(1.0, f))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v):
        try:
            return Category(v)
        except (ValueError, KeyError):
            return Category.OTHER

    @field_validator("severity_hint", mode="before")
    @classmethod
    def _coerce_severity(cls, v):
        try:
            return SeverityHint(v)
        except (ValueError, KeyError):
            return SeverityHint.STABLE

    @field_validator("reply_kind", mode="before")
    @classmethod
    def _coerce_reply_kind(cls, v):
        try:
            return ReplyKind(v)
        except (ValueError, KeyError):
            return ReplyKind.OTHER

    @field_validator("asked_fields", mode="before")
    @classmethod
    def _coerce_asked_fields(cls, v):
        if not isinstance(v, list):
            return []
        # 짧은 키워드 문자열만, 공백 제거 + 빈값/중복 제거(최대 6개).
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out[:6]

    @field_validator("summary_delta", "assistant_reply", "reason", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return "" if v is None else str(v)

    def model_post_init(self, __context) -> None:
        # 경과가 아니면 summary_delta는 항상 빈 문자열로 강제.
        if not self.is_followup:
            object.__setattr__(self, "summary_delta", "")


# --- 키워드 fallback (LLM/JSON 실패 시) ---------------------------------

SYMPTOM_KEYWORDS = (
    # 소화기
    "구토", "토", "설사", "혈변", "혈뇨", "구역질", "헛구역", "배가 아파", "배아파", "배탈",
    # 호흡·신경
    "피", "기침", "숨", "호흡", "발작", "쓰러", "의식", "재채기", "콧물", "코가 막",
    # 전신 — 증상 변화 표현 추가
    "축 처", "축처", "무기력", "떨림", "몸이 이상", "상태가 이상", "이상한 것 같", "뭔가 달라",
    "평소랑 달라", "달라 보여", "변한 것 같", "좀 이상", "상태가 안 좋", "기운 없", "힘이 없",
    "심해", "나빠", "악화", "나아지", "호전", "아직도", "여전히", "계속 그래", "더 나아",
    # 식욕·에너지 — 사료/거부/누움 표현 추가
    "밥", "식욕", "물", "입맛", "잘 안 먹", "밥을 안", "먹질 않", "안 마셔", "물을 안",
    "사료", "기력이", "활동이 줄", "누워만", "주저앉", "먹기를 거부", "입도 안 대", "먹으려 하지",
    # 배설
    "소변", "대변", "오줌", "똥", "변이", "혈이 섞", "소변 색", "소변을 못",
    # 통증·행동 — 계단/머리기울임/앉기 표현 추가
    "통증", "아파", "절어", "절뚝", "핥", "긁어", "낑낑", "끙끙", "낑낑거", "비명", "끙",
    "다리를 절", "다리가 아", "허리가 아", "움직이기 싫어", "자꾸 넘어",
    "계단을 못", "앉지를 못", "기울여", "머리가 기울", "비틀거", "발을 못 디",
    # 약물 반응
    "처방", "항생제", "주사 맞", "약 먹", "약을 먹", "약이 안 듣", "부작용",
    # 눈·귀·피부
    "눈곱", "눈이 충혈", "눈물이", "귀가 가려", "귀를 긁", "피부가 빨개", "털이 빠", "상처가",
)
URGENT_KEYWORDS = (
    # 호흡·신경
    "호흡곤란", "숨", "헐떡", "혀가 파", "혀가 보라", "잇몸이 파", "입술이 파",
    "발작", "쓰러", "의식",
    # 출혈
    "피 섞", "피가 섞", "혈변", "혈뇨",
    # 반복 구토
    "계속 토", "반복",
    # 배뇨폐색
    "소변을 못", "소변 못", "소변 색",
)
HOSPITAL_KEYWORDS = (
    "병원", "주소", "위치", "몇 시", "영업", "운영", "전화", "주차", "휴진",
)


def keyword_fallback(message: str) -> FollowupClassification:
    """LLM 출력이 깨졌을 때 메시지 키워드로 보수적으로 분류."""
    text = message or ""

    if any(k in text for k in HOSPITAL_KEYWORDS):
        return FollowupClassification(
            is_followup=False,
            category=Category.HOSPITAL_INFO,
            severity_hint=SeverityHint.STABLE,
            assistant_reply="병원 정보는 바로 확인해 알려드릴게요.",
            reason="fallback: 병원 정보 키워드 감지",
        )

    if any(k in text for k in SYMPTOM_KEYWORDS):
        urgent = any(k in text for k in URGENT_KEYWORDS)
        return FollowupClassification(
            is_followup=True,
            category=Category.SYMPTOM_CHANGE,
            severity_hint=SeverityHint.URGENT_POSSIBLE if urgent else SeverityHint.WORSE,
            summary_delta=text.strip()[:100],
            assistant_reply="말씀해주신 변화가 걱정되셨겠어요. 상태가 더 달라지면 바로 알려주세요.",
            reason="fallback: 증상 키워드 감지(보수적으로 저장)",
        )

    return FollowupClassification(
        is_followup=False,
        category=Category.IRRELEVANT,
        severity_hint=SeverityHint.STABLE,
        assistant_reply="예약 전후로 아이 상태가 달라지면 언제든 알려주세요.",
        reason="fallback: 경과/병원 키워드 없음 → 저장 안 함",
    )


def parse_classification(raw: dict | None, message: str) -> FollowupClassification:
    """LLM이 준 dict를 검증. 실패하면 키워드 fallback."""
    if not isinstance(raw, dict):
        return keyword_fallback(message)
    try:
        return FollowupClassification(**raw)
    except Exception:
        return keyword_fallback(message)


# --- 보호자 응답 안전 보정 ------------------------------------------------

# urgent_possible인데 LLM이 안내를 빠뜨렸을 때 코드가 덧붙이는 문구.
# '가까운 응급병원으로 가라'처럼 겁주거나 다른 병원으로 보내지 않는다 — 우리 병원에 예약된
# 보호자이므로, 공감(아래 fallback) 뒤에 '더 빠른 진료'를 제안한다('더 빠른 시간 찾기' pill과 짝).
URGENT_SAFETY_NOTE = "더 빠른 예약 시간을 찾아봐 드릴까요?"


def _has_emergency_guidance(text: str) -> bool:
    """응급 경과 답변에 이미 '더 빠른 진료'(앞당김 제안/병원 즉시 연락) 유도가 있는지 판단."""
    t = text or ""
    if any(k in t for k in ("빠른 예약", "빠른 시간", "앞당", "더 빨리", "더 일찍")):
        return True
    has_place = ("병원" in t) or ("내원" in t) or ("응급" in t)
    has_now = any(k in t for k in ("바로", "즉시", "지금", "당장"))
    has_contact = any(k in t for k in ("연락", "전화", "내원"))
    return has_place and has_now and has_contact


def ensure_safe_reply(cls: "FollowupClassification", fallback: str) -> str:
    """보호자에게 보일 최종 reply 생성.

    1) assistant_reply가 있으면 그걸 우선 사용, 비어 있으면 fallback.
    2) urgent_possible인데 응급 안내가 빠져 있으면 짧은 안전 문구를 덧붙인다.
    """
    reply = (cls.assistant_reply or "").strip() or fallback
    if cls.severity_hint == SeverityHint.URGENT_POSSIBLE and not _has_emergency_guidance(reply):
        reply = f"{reply} {URGENT_SAFETY_NOTE}".strip()
    return reply


# --- 저장 안내 반복 제거 ---------------------------------------------------

_SAVE_NOTICE_PATTERNS = (
    r"기록\s*해\s*둘게요",
    r"기록\s*해\s*두겠습니다",
    r"남겨\s*둘게요",
    r"남겨\s*두겠습니다",
    r"정리\s*해\s*둘게요",
    r"정리\s*해\s*두겠습니다",
    r"수의사\s*선생님이\s*확인할\s*수\s*있게",
    r"수의사(?:\s*선생님)?(?:에게|께)?\s*전달",
    r"진료\s*메모에\s*반영",
    r"확인할\s*수\s*있도록\s*전달",
    r"전달(?:될|해\s*둘|해\s*두|하겠)",
)
_SAVE_NOTICE_RE = re.compile("|".join(f"(?:{p})" for p in _SAVE_NOTICE_PATTERNS))
_SENTENCE_RE = re.compile(r"[^.!?。！？\n]+(?:[.!?。！？]+|$)")
_TOO_SHORT_EMPATHY_RE = re.compile(
    r"^(?:많이\s*)?(?:걱정|놀라|불안|속상|답답)(?:되셨겠어요|하셨겠어요|스러우셨겠어요)[.!?。！？]?$"
)
_BROKEN_END_RE = re.compile(r"(?:수\s*있게|있도록|에게|께|에|을|를|은|는|이|가|도|만|로|으로|와|과|고|며|지만)$")
_SAVE_NOTICE_QUESTION_RE = re.compile(
    r"(기록|저장|전달|메모|남(?:아|나요|겨)|수의사|선생님|보여\s*주|볼\s*수|확인).*(\?|나요|될까요|되나요|하나요|해요|죠|지요)"
)


def allows_save_notice_question(user_message: str) -> bool:
    """보호자가 기록/전달 여부를 직접 물은 경우만 저장 안내를 허용한다."""
    text = re.sub(r"\s+", " ", user_message or "").strip()
    if not text:
        return False
    return bool(_SAVE_NOTICE_QUESTION_RE.search(text))


def strip_save_notice(reply: str, *, allow_save_notice: bool = False) -> str:
    """저장/전달 완료를 알리는 문장만 제거한다.

    보호자가 기록 여부를 직접 물은 경우에는 답변 목적 자체가 저장 안내일 수 있어 그대로 둔다.
    """
    text = re.sub(r"\s+", " ", reply or "").strip()
    if allow_save_notice or not text:
        return text

    sentences = [m.group(0).strip() for m in _SENTENCE_RE.finditer(text)]
    if not sentences:
        return "" if _SAVE_NOTICE_RE.search(text) else text

    kept = [s for s in sentences if not _SAVE_NOTICE_RE.search(s)]
    return " ".join(kept).strip()


def needs_saved_reply_fallback(reply: str, user_message: str = "") -> bool:
    """저장 안내 제거 뒤 보호자에게 보일 답변으로 부족하면 fallback으로 교체한다."""
    text = re.sub(r"\s+", " ", reply or "").strip()
    if not text:
        return True
    if len(text) < 8:
        return True
    if _TOO_SHORT_EMPATHY_RE.fullmatch(text):
        return True
    if _BROKEN_END_RE.search(text):
        return True
    # 저장 문장 제거 뒤 남은 말이 사용자 발화와 무관한 접속/확인 토막이면 교체한다.
    weak_fragments = {"네", "알겠어요", "확인했어요", "좋아요", "그렇군요", "말씀해주셔서 고마워요"}
    if text.rstrip(".!?。！？") in weak_fragments:
        return True
    return False


# --- 누적 경과 메모 머지 --------------------------------------------------

def merge_followup_summary(old_summary: str | None, delta: str | None, max_len: int = 400) -> str:
    """이전 누적 메모에 이번 변화를 이어 붙인다(결정론).

    수의사용 메모라 최신 변화가 잘 보이게 뒤에 붙이고, 너무 길면 앞부분을 잘라낸다.
    """
    old = (old_summary or "").strip()
    new = (delta or "").strip()
    if not new:
        return old
    if not old:
        return new
    merged = f"{old} / {new}"
    if len(merged) > max_len:
        merged = merged[-max_len:]
    return merged
