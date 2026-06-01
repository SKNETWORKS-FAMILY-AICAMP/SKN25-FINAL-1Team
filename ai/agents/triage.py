"""Triage Agent — Modified VTL 5단계 문진 분류.

참고 논문:
- "Basic triage in dogs and cats" (생리학적 파라미터 기반)
- "Evaluation of a veterinary triage list modified from a human five-point triage system
   in 485 dogs and cats" (Modified VTL 5단계)
- Wei et al. 2022 (Chain-of-Thought)
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from .base import call_openai

logger = logging.getLogger(__name__)


def build_triage_prompt(pet: dict, rules: dict | None = None, emr_history: list | None = None) -> str:
    """캐논 트리아지 프롬프트(app.prompts.triage_prompt)를 재사용한다.

    실제 챗봇 흐름(chat.py)과 이 agent 경로가 동일한 단일 프롬프트를 쓰도록
    dict 형태 pet/emr_history를 캐논 빌더가 기대하는 형식으로 어댑팅한다.
    """
    from datetime import date
    from types import SimpleNamespace

    from app.prompts.triage_prompt import _build_triage_system_prompt

    # 캐논 빌더는 birth_date.year로 나이를 계산하므로 age → birth_date로 역산
    age = pet.get("age")
    try:
        birth_date = date(date.today().year - int(age), 1, 1) if age not in (None, "?", "") else None
    except (TypeError, ValueError):
        birth_date = None

    pet_ns = SimpleNamespace(
        petname=pet.get("name", "알 수 없음"),
        species=pet.get("species", "dog"),
        breed=pet.get("breed", "알 수 없음"),
        birth_date=birth_date,
        gender=pet.get("gender", "미상"),
        weight_kg=pet.get("weight"),
    )

    # emr_history(list) → 캐논이 기대하는 {"patient_context": {"emr_history": [...]}} 형태로 래핑
    patient_context = {"patient_context": {"emr_history": emr_history}} if emr_history else None

    return _build_triage_system_prompt(pet_ns, patient_context=patient_context)


# 캐논 정의를 재노출 — 기존 import 경로(ai.agents.triage.FORCE_COMPLETE_SUFFIX) 호환 유지
from app.prompts.triage_prompt import FORCE_COMPLETE_SUFFIX  # noqa: E402


# urgency_level_num → 라벨. LLM 출력 방어용 단일 소스.
_URGENCY_LABELS = {1: "즉시", 2: "응급", 3: "긴급", 4: "준긴급", 5: "비긴급"}


def _coerce_collected_info(info: dict | None) -> dict | None:
    """LLM이 반환한 collected_info의 응급도 필드를 안전 범위로 보정한다.

    잘못된 enum/범위 밖 숫자가 예약 흐름으로 그대로 흐르지 않도록,
    throw 대신 보수적으로 클램프한다(불확실하면 더 긴급한 쪽으로).
    """
    if not isinstance(info, dict):
        return info

    raw = info.get("urgency_level_num")
    try:
        num = int(raw)
    except (TypeError, ValueError):
        num = 2  # 파싱 불가 → 보수적으로 응급(2)
    num = max(1, min(5, num))  # 1~5 범위 클램프

    info["urgency_level_num"] = num
    # 라벨이 비었거나 숫자와 불일치하면 숫자 기준으로 동기화
    if info.get("urgency_level") not in _URGENCY_LABELS.values():
        info["urgency_level"] = _URGENCY_LABELS[num]
    return info


async def run_triage(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """Triage Agent 실행 — BackgroundTasks에서 호출됩니다."""
    pet = payload.get("pet", {})
    messages = payload.get("messages", [])
    rules = payload.get("rules")
    emr_history = payload.get("emr_history")

    update_step("증상 키워드 추출 중...")
    system = build_triage_prompt(pet, rules, emr_history)

    update_step("응급도 분류 중...")
    result = await call_openai(messages, system, model="gpt-4o-mini", max_tokens=2000)

    # LLM 출력 방어: 완료된 문진의 응급도 필드를 안전 범위로 보정
    if isinstance(result, dict) and result.get("collected_info"):
        result["collected_info"] = _coerce_collected_info(result["collected_info"])

    update_step("문진 요약 생성 중...")
    logger.info(f"[Triage] emrid={emrid} urgency={(result.get('collected_info') or {}).get('urgency_level_num')}")

    return {"agent": "triage", "emrid": emrid, **result}
