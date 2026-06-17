import json
import logging

from ai.llm import call_llm_json

from ai.agents.chart.prompts import CHART_PROMPT

logger = logging.getLogger(__name__)


# 문진 대화 포맷 (최근 14턴)
def _format_chat_history(chat_history: list[dict]) -> str:
    if not chat_history:
        return "[챗봇 전체 문진 대화]\n기록 없음"
    lines = ["[챗봇 전체 문진 대화]"]
    for idx, message in enumerate(chat_history[-14:], start=1):
        role = "보호자" if message.get("role") == "user" else "챗봇"
        content = " ".join(str(message.get("content") or "").split())
        if content:
            lines.append(f"{idx}. {role}: {content[:500]}")
    return "\n".join(lines)


# RAG 유사사례 포맷 (감별진단 보조용 — 진단 확정 근거 아님)
def _format_rag(rag_context: list[dict] | None) -> str:
    items = rag_context or []
    if not items:
        return "[유사 상담사례 참고] 없음"
    lines = ["[유사 상담사례 참고 — 감별진단 보조용. 진단 확정 근거 아님]"]
    for idx, item in enumerate(items[:3], start=1):
        dept = item.get("department") or "?"
        disease = item.get("disease") or "?"
        sim = item.get("similarity")
        sim_txt = f"{sim:.2f}" if isinstance(sim, (int, float)) else "?"
        out = " ".join(str(item.get("output_text") or "").split())[:200]
        lines.append(f"{idx}. [{dept}/{disease}] (유사도 {sim_txt}) {out}")
    return "\n".join(lines)


# CNN 피부/안구 예측 요약
def _format_cnn(triage: dict) -> str:
    preds = triage.get("photo_predictions") or []
    skin = [p["prediction"] for p in preds if p.get("model_type") != "eye" and p.get("prediction")]
    eye = [p["prediction"] for p in preds if p.get("model_type") == "eye" and p.get("prediction")]
    parts = []
    if skin:
        parts.append(f"피부[{'/'.join(skin)}]")
    if eye:
        parts.append(f"안구[{'/'.join(eye)}]")
    return " / ".join(parts) if parts else "없음"


class ChartAgent:
    """수의사용 SOAP 차트 초안 생성 에이전트 (LLM, env 모델)."""

    # 차트 작성
    async def generate(
        self,
        pet: dict,
        triage: dict,
        patient_context: dict | None = None,
        chat_history: list[dict] | None = None,
        rag_context: list[dict] | None = None,
    ) -> dict:
        prompt = CHART_PROMPT.format(
            pet_info=self._pet_info(pet),
            triage_section=self._triage_section(triage),
            cnn_section=_format_cnn(triage),
            chat_section=_format_chat_history(chat_history or []),
            history_section=self._history_section(patient_context),
            rag_section=_format_rag(rag_context),
        )
        try:
            result = await call_llm_json(prompt=prompt, temperature=0.2)
            logger.info("[chart] 생성 완료 suspected=%s",
                        (result.get("intake_summary") or {}).get("suspected_diseases"))
            return result
        except Exception as e:
            logger.warning("[chart] 생성 실패: %s", e)
            return {}

    # 반려동물 정보 한 줄
    def _pet_info(self, pet: dict) -> str:
        return (f"이름: {pet.get('name')} / 품종: {pet.get('breed', '알 수 없음')} / "
                f"나이: {pet.get('age', '?')}세 / 성별: {pet.get('gender', '미상')} / "
                f"체중: {pet.get('weight', '?')}kg")

    # 트리아지 요약 섹션
    def _triage_section(self, triage: dict) -> str:
        return "\n".join([
            f"응급도: {triage.get('urgency_level')} (VTL Level {triage.get('urgency_level_num')})",
            f"주요증상: {', '.join(triage.get('symptom_keywords') or [])}",
            f"증상시작: {triage.get('symptom_onset', '')}",
            f"의심질환: {', '.join(triage.get('suspected_diseases') or [])}",
            f"Red Flags: {', '.join(triage.get('red_flags') or []) or '없음'}",
            f"문진요약: {triage.get('symptom_summary', '')}",
        ])

    # 과거 EMR 이력 섹션
    def _history_section(self, patient_context: dict | None) -> str:
        if patient_context and patient_context.get("patient_context", {}).get("emr_history"):
            return "[과거 임상 컨텍스트 및 병력]\n" + json.dumps(
                patient_context, ensure_ascii=False, indent=2
            )
        return "[과거 진료 기록 없음 - 초진으로 간주]"
