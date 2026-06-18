"""경과 필터 LLM 출력 스키마 + 안전 파싱/머지 유틸.  담당: B

- LLM은 JSON만 뱉게 시키고, 여기서 Pydantic으로 검증한다.
- enum이 틀리거나 JSON 파싱이 깨지면 키워드 기반으로 보수적으로 분류(fallback).
- followup_summary 누적 머지도 코드에서 결정론적으로 처리.
"""
from __future__ import annotations

from enum import Enum

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
    """
    is_followup: bool = False
    category: Category = Category.OTHER
    severity_hint: SeverityHint = SeverityHint.STABLE
    summary_delta: str = ""
    assistant_reply: str = ""
    reason: str = ""

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
    "구토", "토", "설사", "혈변", "피", "기침", "숨", "호흡", "발작", "쓰러",
    "축 처", "축처", "무기력", "밥", "식욕", "물", "소변", "대변", "통증", "아파", "떨림",
)
URGENT_KEYWORDS = (
    "호흡곤란", "숨", "발작", "쓰러", "의식", "피 섞", "혈변", "계속 토", "반복",
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
            assistant_reply="병원 정보 확인이 필요한 질문이네요. 안내 담당이 이어서 도와드릴 수 있게 넘길게요.",
            reason="fallback: 병원 정보 키워드 감지",
        )

    if any(k in text for k in SYMPTOM_KEYWORDS):
        urgent = any(k in text for k in URGENT_KEYWORDS)
        return FollowupClassification(
            is_followup=True,
            category=Category.SYMPTOM_CHANGE,
            severity_hint=SeverityHint.URGENT_POSSIBLE if urgent else SeverityHint.WORSE,
            summary_delta=text.strip()[:100],
            assistant_reply="말씀해주신 변화가 걱정되셨겠어요. 수의사 선생님이 확인할 수 있게 남겨둘게요.",
            reason="fallback: 증상 키워드 감지(보수적으로 저장)",
        )

    return FollowupClassification(
        is_followup=False,
        category=Category.IRRELEVANT,
        severity_hint=SeverityHint.STABLE,
        assistant_reply="예약 전후로 아이 상태가 달라지면 언제든 알려주세요. 진료 때 참고될 수 있게 정리해둘게요.",
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

# urgent_possible인데 LLM이 안내를 빠뜨렸을 때 코드가 덧붙이는 짧은 안전 문구.
URGENT_SAFETY_NOTE = (
    "호흡곤란, 의식저하, 반복 구토, 피 섞인 설사·구토처럼 상태가 심해지면 "
    "병원에 바로 연락해 주세요."
)


def _has_emergency_guidance(text: str) -> bool:
    """답변에 이미 '병원에 연락' 류의 안전 안내가 들어있는지 대략 판단."""
    t = text or ""
    if "병원" not in t:
        return False
    return any(k in t for k in ("연락", "전화", "내원", "방문", "바로", "응급"))


def ensure_safe_reply(cls: "FollowupClassification", fallback: str) -> str:
    """보호자에게 보일 최종 reply 생성.

    1) assistant_reply가 있으면 그걸 우선 사용, 비어 있으면 fallback.
    2) urgent_possible인데 응급 안내가 빠져 있으면 짧은 안전 문구를 덧붙인다.
    """
    reply = (cls.assistant_reply or "").strip() or fallback
    if cls.severity_hint == SeverityHint.URGENT_POSSIBLE and not _has_emergency_guidance(reply):
        reply = f"{reply} {URGENT_SAFETY_NOTE}".strip()
    return reply


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
