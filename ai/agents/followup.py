"""Followup Monitoring Agent — 예약 확정 후 경과 모니터링.

'동적 증상군'(발작·반복 구토·진행성 출혈·호흡 이상·의식 저하·독성물질 등)으로
need_followup=true 판정된 케이스에만 활성화됩니다. 활성 기준은
ai.triage.engine.compute_need_followup가 단일 판정합니다.
보호자가 보낸 텍스트만 모아 임상적으로 의미 있는 변화를 한 줄로 요약해 수의사에게
전달합니다(사진은 판단하지 않음). 반려동물 건강과 무관한 발화는 요약에 반영하지 않습니다.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from .base import call_openai

logger = logging.getLogger(__name__)


def build_followup_prompt(
    pet: dict,
    triage_info: dict,
    appointment_slot: dict | None = None,
    accumulated_summary: str | None = None,
    patient_context: dict | None = None,
) -> str:
    appt_date = (appointment_slot or {}).get("date") or "예약일"

    return f"""당신은 MediPaw 경과 모니터링 AI입니다.
예약 확정 후 보호자가 전송하는 경과 보고(텍스트·사진)를 분석하여 응답하고,
수의사에게 전달할 누적 요약을 업데이트합니다.

[반려동물 정보]
이름: {pet.get('name')} / 품종: {pet.get('breed', '알 수 없음')} / 나이: {pet.get('age', '?')}세 / 체중: {pet.get('weight', '?')}kg

[초기 문진 요약]
주증상: {triage_info.get('chief_complaint', '')}
응급도: {triage_info.get('urgency_level')} (Level {triage_info.get('urgency_level_num')})
증상 키워드: {', '.join(triage_info.get('symptom_keywords') or [])}
의심 질환: {', '.join(triage_info.get('suspected_diseases') or [])}
모니터링 이유: {triage_info.get('followup_reason', '')}

[예약 정보]
예약일: {appt_date}

[과거 병력 컨텍스트]
{json.dumps(patient_context, ensure_ascii=False) if patient_context else '초진 (과거 기록 없음)'}

[누적 경과 요약 — 이전 대화에서 추출된 임상 메모]
{accumulated_summary or '아직 경과 보고 없음 — 이번이 첫 보고입니다.'}
※ medical_summary는 위 누적 요약에 이번 보고를 통합한 '전체 경과 한 줄'입니다. 누적 요약을 덮어쓰듯 갱신하세요.
※ 보호자가 이번에 여러 내용을 한꺼번에 보냈다면 임상적으로 의미 있는 변화만 골라 하나의 짧은 문장으로 묶으세요.

[역할]
1. 보호자의 경과 보고를 공감적으로 수신하고 간단히 응답한다 (guardian_message)
2. 새 증상·악화 징후가 감지되면 내원이 필요한지 부드럽게 판단한다 (followup_recommended)
3. 상황에 맞는 후속 행동을 추천한다 (recommended_actions: "keep_schedule", "fast_booking" 중 선택)
4. 임상적으로 의미 있는 텍스트만 medical_summary에 한 줄로 요약한다 (사진은 판단하지 않음)

[medical_summary 작성 기준 — 수의사용 임상 메모]
포함 O: 증상 변화(발작 빈도·지속시간, 구토·설사 횟수, 출혈량), 새 신체 징후, 식욕·수분·배변 변화, 투약 반응
포함 X: 보호자 감정 표현, 일상 호소, 의학 무관 맥락, 사진 내용 추정·판단, 이전 요약 반복
길이: 정확히 한 문장(80자 이내). 전체 경과의 핵심 변화만 압축. 평서형.
※ 반려동물 건강·증상과 무관한 발화(잡담, 일반 지식 질문 등)는 medical_summary에 절대 반영하지 말 것. 관련 내용이 전혀 없으면 medical_summary는 빈 문자열("")로 두세요.

[보호자 guardian_message 금지 사항]
- 질환명 진단, 증상 원인 추정, 예후 평가, 경중 판단 금지
- 강한 어조("응급입니다", "위험합니다", "즉시 내원하세요", "생명 위협") 절대 사용 금지.
- 완화된 표현 허용: "빠른 확인이 필요해 보여요", "예약 일정을 앞당겨 확인해보는 것을 권장드려요"

[응답 형식 - JSON만 출력]
일반 경과 보고:
{{
  "guardian_message": "보호자 응답 (공감적, 1~2문장, 진단·권유 금지)",
  "followup_recommended": false,
  "recommended_actions": ["keep_schedule"],
  "medical_summary": "수의사용 전체 경과 한 줄 요약(한 문장, 80자 이내)."
}}

일정 조정 필요 시 (악화 징후 감지):
{{
  "guardian_message": "증상 변화가 있어 빠른 확인이 필요해 보여요. 가능한 빠른 예약 시간을 다시 확인해드릴게요.",
  "followup_recommended": true,
  "recommended_actions": ["fast_booking"],
  "medical_summary": "상태 변화 감지 — 한 줄 임상 경과 요약. 빠른 일정 확인 권장됨."
}}"""


async def run_followup(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """Followup Agent 실행."""
    pet = payload.get("pet", {})
    triage_info = payload.get("triage_info") or payload.get("triage_result") or {}
    appointment_slot = payload.get("appointment_slot")
    accumulated_summary = payload.get("accumulated_summary")
    patient_context = payload.get("patient_context")
    messages = payload.get("messages", [])

    update_step("경과 보고 분석 중...")

    # 반려동물 건강과 무관한 보고(잡담·일반 지식 질문 등)는 요약·판단하지 않고 리다이렉트한다.
    # triage 챗봇과 동일한 주제 필터를 재사용한다. (사진은 텍스트가 아니므로 검사 대상 아님)
    user_texts = [
        str(m.get("content") or "").strip()
        for m in messages
        if m.get("role") == "user" and str(m.get("content") or "").strip()
    ]
    combined_report = " ".join(user_texts).strip()
    if combined_report:
        from ..triage.session import _is_offtopic

        if await _is_offtopic(combined_report, pet.get("species")):
            logger.info(f"[Followup] emrid={emrid} off-topic 보고 — 요약 생략")
            return {
                "agent": "followup",
                "emrid": emrid,
                "guardian_message": "경과와 관련된 내용을 보내주시면 도와드릴게요. 증상이나 상태 변화를 알려주세요.",
                "followup_recommended": False,
                "recommended_actions": ["keep_schedule"],
                "medical_summary": "",  # 무관 보고 — 누적 요약 갱신 안 함
            }

    system = build_followup_prompt(pet, triage_info, appointment_slot, accumulated_summary, patient_context)

    # 롤링 6턴 윈도우 — 오래된 대화는 누적 요약으로 대체
    MAX_TURNS = 6
    trimmed = messages[-MAX_TURNS:] if len(messages) > MAX_TURNS else messages

    result = await call_openai(trimmed, system, max_tokens=800, agent="followup")

    if not result.get("medical_summary") and result.get("followup_summary"):
        result["medical_summary"] = result["followup_summary"]
    if result.get("medical_summary"):
        # 한 줄 보장 — 공백 정규화 후 80자 컷
        result["medical_summary"] = " ".join(str(result["medical_summary"]).split())[:80]

    update_step("경과 요약 업데이트 중...")
    logger.info(
        f"[Followup] emrid={emrid} followup_recommended={result.get('followup_recommended', False)}"
    )

    return {"agent": "followup", "emrid": emrid, **result}
