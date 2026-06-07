"""Chart Agent — 수의사용 SOAP 차트 초안 생성.

Parent Agent Orchestration 패턴으로 6단계 추론을 거쳐
SOAP 차트, 감별진단, 처방 초안을 생성합니다.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from .base import call_openai_once

logger = logging.getLogger(__name__)


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


def _format_rag_for_chart(rag_context: list[dict] | None) -> str:
    """공용 RAG 레이어가 모은 유사 상담사례를 차트 프롬프트용으로 압축.

    감별진단 보조 '참고용'일 뿐 진단 확정 근거가 아님을 명시한다.
    """
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


def build_chart_prompt(
    pet: dict,
    triage_result: dict,
    patient_context: dict | None = None,
    chat_history: list[dict] | None = None,
    rag_context: list[dict] | None = None,
) -> str:
    preds = triage_result.get("photo_predictions") or []
    skin_preds = [p["prediction"] for p in preds if p.get("model_type") != "eye" and p.get("prediction")]
    eye_preds = [p["prediction"] for p in preds if p.get("model_type") == "eye" and p.get("prediction")]
    cnn_parts = []
    if skin_preds:
        cnn_parts.append(f"피부[{'/'.join(skin_preds)}]")
    if eye_preds:
        cnn_parts.append(f"안구[{'/'.join(eye_preds)}]")
    cnn_section = " / ".join(cnn_parts) if cnn_parts else "없음"

    if patient_context and patient_context.get("patient_context", {}).get("emr_history"):
        history_section = (
            f"[과거 임상 컨텍스트 및 병력]\n" + json.dumps(
                patient_context, ensure_ascii=False, indent=2
            )
        )
    else:
        history_section = "[과거 진료 기록 없음 - 초진으로 간주]"

    chat_section = _format_chat_history(chat_history or [])
    rag_section = _format_rag_for_chart(rag_context)

    return f"""당신은 MediPaw 수의학 차트 생성 AI입니다.
문진 결과를 기반으로 SOAP 형식 EMR 차트 초안을 생성합니다.
이 차트는 수의사가 최종 확인·수정합니다. 확정적 진단을 단언하지 마세요.

[반려동물 정보]
이름: {pet.get('name')} / 품종: {pet.get('breed', '알 수 없음')} / 나이: {pet.get('age', '?')}세 / 성별: {pet.get('gender', '미상')} / 체중: {pet.get('weight', '?')}kg

[트리아지 결과]
응급도: {triage_result.get('urgency_level')} (VTL Level {triage_result.get('urgency_level_num')})
주요증상: {', '.join(triage_result.get('symptom_keywords') or [])}
증상시작: {triage_result.get('symptom_onset', '')}
의심질환: {', '.join(triage_result.get('suspected_diseases') or [])}
Red Flags: {', '.join(triage_result.get('red_flags') or []) or '없음'}
문진요약: {triage_result.get('symptom_summary', '')}
AI CNN 모델 분석 결과: {cnn_section}

{chat_section}

{history_section}

{rag_section}

[차트 생성 흐름 - Chart Parent Agent Orchestration]
STEP 1: 증상 Entity 추출 (발생시점, 빈도, 강도, 동반증상, 환경요인)
STEP 2: 증상 타임라인 구성 (언제부터 → 어떻게 진행 → 현재 상태)
STEP 3: 감별진단 가설 2-3개 생성 (확률 높은 순)
STEP 4: 의학적 근거 검토 (각 감별진단의 증거/반증)
STEP 5: 누락 정보 탐지 (추가 필요한 검사/정보)
STEP 6: 최종 SOAP 차트 초안 생성

[응답 형식 - JSON만 출력]
{{
  "thinking": "STEP 1~6 추론 과정 (내부용)",
  "soap": {{
    "S": "Subjective. 챗봇 전체 문진 대화의 보호자 발화를 빠짐없이 반영해 SOAP 문장으로 정리. 주증상, 시작 시점, 경과, 동반증상/부정증상, 보호자가 모른다고 한 정보까지 포함.",
    "O": "Objective. 실제 검사 전이므로 '내원 시 확인 필요'를 명시하고 예상 관찰/신체검사 항목을 정리.",
    "A": "Assessment. 감별진단 2~3개와 근거/반증. 확정 진단 금지.",
    "P": "Plan. 권장 검사, 처치, 보호자 교육, 재진/모니터링 계획. 처방은 수의사 확인 전제로 작성."
  }},
  "differential_diagnosis": [
    {{"disease": "질환명", "probability": "높음/중간/낮음", "reasoning": "근거", "against": "반증"}}
  ],
  "recommended_tests": ["CBC/Chemistry", "복부 X-ray"],
  "red_flags_confirmed": ["혈변 의심"],
  "missing_info": ["체온 측정값", "최근 식이 변화 여부"],
  "vet_questions": [
    "수의사가 내원 시 보호자에게 직접 확인해야 할 질문 3~5개",
    "감별진단 구분에 필요하거나 missing_info 해소에 유용한 질문을 구체적으로 작성"
  ],
  "prescription_draft": {{
    "diagnosis": "추정 진단",
    "medications": [
      {{"name": "약품명", "dosage": "용량", "frequency": "횟수", "duration": "기간", "route": "경구/주사"}}
    ],
    "cautions": ["주의사항"]
  }}
}}"""


async def run_chart(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """Chart Agent 실행 — gpt-4o 사용 (추론 부담이 큰 작업)."""
    pet = payload.get("pet", {})
    triage_result = payload.get("triage_result", {})
    patient_context = payload.get("patient_context")
    chat_history = payload.get("chat_history", [])
    rag_context = payload.get("rag_context")

    update_step("증상 엔티티 추출 중...")
    system = build_chart_prompt(pet, triage_result, patient_context, chat_history, rag_context)

    update_step("SOAP 차트 초안 작성 중...")
    result = await call_openai_once(
        "SOAP 차트를 생성해주세요.",
        system,
        model="gpt-4o",
        max_tokens=1800,
        agent="chart",
    )

    update_step("최종 차트 생성 중...")
    logger.info(f"[Chart] emrid={emrid} missing_info={result.get('missing_info')}")

    return {"agent": "chart", "emrid": emrid, "scheduleid": scheduleid, **result}
