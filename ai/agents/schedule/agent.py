import json
import logging

from ai.llm import call_llm_structured

from ai.agents.schedule.prompts import DURATION_PROMPT, CARE_TIPS_PROMPT

logger = logging.getLogger(__name__)

# duration 산정 결과 구조 강제 (누락/오염 방지)
_DURATION_SCHEMA = {
    "title": "DurationEstimate",
    "type": "object",
    "properties": {
        "estimated_duration_min": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["estimated_duration_min", "reasoning"],
    "additionalProperties": False,
}

_MIN_DURATION = 15
_MAX_DURATION = 60

# 내원 전 주의사항 구조 강제
_CARE_TIPS_SCHEMA = {
    "title": "CareTips",
    "type": "object",
    "properties": {
        "tips": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tips"],
    "additionalProperties": False,
}

# 응급도 라벨 → fallback 기본 시간 (LLM 실패 시에만 사용)
_FALLBACK_BASE = {"RED": 40, "ORANGE": 40, "YELLOW": 30, "GREEN": 20}


class ScheduleAgent:
    """진료 예상 소요시간 산정 전용 에이전트 (LLM).

    슬롯 추천(어느 날·몇 시)은 결정론 로직(crud.recommend_slots)이 담당하고,
    이 에이전트는 'estimated_duration_min' 하나만 책임진다.
    """

    # 진료 예상 소요시간 산정 (LLM)
    async def estimate_duration(self, pet: dict, triage: dict) -> dict:
        is_initial = bool(triage.get("is_initial_visit", True))

        prompt = DURATION_PROMPT.format(
            pet=json.dumps(pet, ensure_ascii=False, default=str),
            triage=json.dumps(self._triage_view(triage), ensure_ascii=False, default=str),
            visit_type="초진" if is_initial else "재진",
        )

        try:
            data = await call_llm_structured(prompt=prompt, schema=_DURATION_SCHEMA)
            minutes = self._normalize(data.get("estimated_duration_min"))
            reasoning = (data.get("reasoning") or "").strip()
        except Exception as e:
            logger.warning("[schedule] duration LLM 실패, fallback 사용: %s", e)
            minutes = self._fallback(triage, is_initial)
            reasoning = "LLM 실패 — 응급도 기반 기본값"

        logger.info("[schedule] estimated_duration_min=%s initial=%s", minutes, is_initial)
        return {
            "estimated_duration_min": minutes,
            "is_initial_visit": is_initial,
            "reasoning": reasoning,
        }

    # 내원 전 주의사항 생성 (LLM) — 증상 기반 가정 케어 팁 2~4개
    async def care_guidance(self, triage: dict) -> list[str]:
        prompt = CARE_TIPS_PROMPT.format(
            triage=json.dumps(self._triage_view(triage), ensure_ascii=False, default=str),
        )
        try:
            data = await call_llm_structured(prompt=prompt, schema=_CARE_TIPS_SCHEMA)
            tips = [str(t).strip() for t in (data.get("tips") or []) if str(t).strip()]
            return tips[:4]
        except Exception as e:
            logger.warning("[schedule] care_guidance LLM 실패: %s", e)
            return []

    # 프롬프트에 넣을 트리아지 핵심 필드만 추림 (키 이름 호환)
    def _triage_view(self, triage: dict) -> dict:
        return {
            "urgency": triage.get("urgency"),
            "score": triage.get("score"),
            "chief_complaints": triage.get("chief_complaints") or triage.get("chief_complaint"),
            "suspected_conditions": triage.get("suspected_conditions") or triage.get("suspected_diseases"),
            "summary": triage.get("triage_summary") or triage.get("symptom_summary"),
        }

    # 15~60분 clamp + 5분 단위 보정 (슬롯 격자 안정화)
    def _normalize(self, raw) -> int:
        try:
            m = int(round(float(raw) / 5.0) * 5)
        except (TypeError, ValueError):
            m = 30
        return max(_MIN_DURATION, min(_MAX_DURATION, m))

    # LLM 실패 시 응급도 기반 기본값
    def _fallback(self, triage: dict, is_initial: bool) -> int:
        base = _FALLBACK_BASE.get(str(triage.get("urgency", "")).upper(), 30)
        return self._normalize(base + (10 if is_initial else 0))
