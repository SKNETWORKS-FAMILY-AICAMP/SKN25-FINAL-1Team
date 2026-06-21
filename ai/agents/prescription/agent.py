"""처방전(Prescription) 에이전트 — 담당 리드. 상세: AGENT_SPECS §7.

★ 챗봇 오케스트레이터와 무관한 별도 트랙. 수의사 EMR 페이지 보조 기능.
문진/진단 + drugsDB 후보 약품을 보고 처방 초안을 생성. 사람(수의사)이 검토·수정(차트처럼 보조).
LLM 호출·프롬프트는 여기에 모은다(엔드포인트는 데이터 수집 + 호출만).
"""
from __future__ import annotations

import logging

from ai.llm import call_llm_structured
from ai.agents.prescription.prompts import GENERATE_PROMPT

logger = logging.getLogger(__name__)

# 처방 초안 구조 강제 (목록 밖 약·비정수 기간 등 오염 방지)
_GENERATE_SCHEMA = {
    "title": "PrescriptionDraft",
    "type": "object",
    "properties": {
        "medications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "form": {"type": "string"},
                    "dosage": {"type": "string"},
                    "frequency": {"type": "string"},
                    "duration": {"type": "integer"},
                },
                "required": ["name", "form", "dosage", "frequency", "duration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["medications"],
    "additionalProperties": False,
}


class PrescriptionAgent:
    """수의사 EMR 처방 보조. SessionContext/AgentResult 안 씀(챗봇 흐름 밖)."""

    async def generate(
        self,
        *,
        pet: dict,
        drug_candidates: list[dict],
        symptoms: list[str] | None = None,
        suspected_diseases: list[str] | None = None,
        doctor_notes: str = "",
    ) -> list[dict]:
        """처방 초안 medication 목록을 만든다.

        반환: [{drug_name, form, dosage, frequency, duration_days}] — 프론트 처방표 계약과 동일.
        약 후보가 없으면 [], LLM 실패 시 [](엔드포인트가 빈 처방으로 처리).
        """
        if not drug_candidates:
            return []

        prompt = GENERATE_PROMPT.format(
            doctor_notes=(doctor_notes or "").strip() or "없음",
            pet_info=self._pet_info(pet or {}),
            symptoms=", ".join(symptoms or []) or "정보 없음",
            suspected=", ".join(suspected_diseases or []) or "정보 없음",
            drug_list=self._format_candidates(drug_candidates),
        )

        try:
            data = await call_llm_structured(prompt=prompt, schema=_GENERATE_SCHEMA, temperature=0.3)
        except Exception as e:
            logger.warning("[prescription] generate LLM 실패: %s", e)
            return []

        meds = data.get("medications") or []
        result = [
            {
                "drug_name": (m.get("name") or "").strip(),
                "form": (m.get("form") or "").strip(),
                "dosage": (m.get("dosage") or "").strip(),
                "frequency": (m.get("frequency") or "").strip(),
                "duration_days": int(m.get("duration") or 0),
            }
            for m in meds
            if (m.get("name") or "").strip()
        ]
        logger.info("[prescription] generate 완료 count=%s", len(result))
        return result

    # 반려동물 정보 한 줄
    def _pet_info(self, pet: dict) -> str:
        species = pet.get("species") or "강아지"
        breed = pet.get("breed") or ""
        weight = pet.get("weight_kg")
        age = pet.get("age")
        return (f"종류/품종: {species} / {breed}\n"
                f"체중: {weight if weight is not None else 0}kg, 나이: {age if age is not None else 0}살")

    # 약물 후보를 프롬프트용 한 줄씩으로 (제품명·성분)
    def _format_candidates(self, drugs: list[dict]) -> str:
        return "\n".join(
            f"- {d.get('name', '')} (성분: {d.get('ingredient_kr') or d.get('ingredient_en') or ''})"
            for d in drugs
        )
