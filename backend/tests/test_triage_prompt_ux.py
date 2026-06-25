from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.agents.followup_filter.prompts import FOLLOWUP_SYSTEM
from ai.agents.triage.prompts import (
    build_question_prompt,
    build_suspected_confirm_message,
    build_suspected_confirm_prompt,
)


def test_question_prompt_requires_single_axis_and_matching_pills():
    prompt = build_question_prompt(
        "군밤이",
        [{"role": "user", "content": "맑은 콧물이 나요"}],
        "맑은 콧물이 나요",
        "RESPIRATORY",
        {},
    )
    assert "질문은 반드시 한 가지 축만" in prompt
    assert "quick_replies는 reply의 질문과 정확히 같은 축" in prompt
    assert '"밥이나 기운"' in prompt


def test_tone_prompt_allows_selective_warmth_without_repetition():
    prompt = build_question_prompt(
        "군밤이",
        [],
        "수술 뒤 밥을 잘 안 먹어서 걱정돼요",
        "GENERAL",
        {},
    )
    assert "수술 후 변화" in prompt
    assert "걱정·불안을 직접 표현" in prompt
    assert "매 턴 반복하지 마" in prompt
    assert "첫 경과 발화, 증상 악화, 수술 후 변화" in FOLLOWUP_SYSTEM


def test_question_prompt_has_pivot_point_warmth():
    # P3. 질문 턴에서도 '전환점에서만 따뜻함'을 명시(중간 정보수집 턴은 생략).
    prompt = build_question_prompt("군밤이", [], "기침을 해요", "RESPIRATORY", {})
    assert "전환점" in prompt
    assert "공감 총량을 늘리려는 게 아니다" in prompt


def test_booking_strength_scales_with_urgency():
    # P2. 마무리 예약 권유 강도가 응급도에 따라 달라진다(결정론 fallback 메시지 기준).
    green = build_suspected_confirm_message("군밤이", [], final_urgency="GREEN", urgency_tier="normal")
    yellow = build_suspected_confirm_message("군밤이", [], final_urgency="YELLOW", urgency_tier="normal")
    red = build_suspected_confirm_message("군밤이", [], final_urgency="RED", urgency_tier="critical")
    # 경증: 가벼운 제안 / 중등도: 진료 권고 + 예약 / 긴급: 빠른 진료 + 가장 빠른 예약
    assert "원하시면 예약도 도와드릴게요." in green and "빠르게" not in green
    assert "한 번 진료" in yellow
    assert "빠르게" in red and "가장 빠른 예약" in red
    assert green != yellow != red


def test_suspect_prompt_injects_urgency_and_tier_instructions():
    # P2. LLM 마무리 프롬프트에 실제 응급도 값이 주입되고, 강도 차등 지시가 들어 있다.
    red_prompt = build_suspected_confirm_prompt(
        "군밤이", "발작을 했어요", ["수의사 답변"],
        final_urgency="RED", urgency_tier="critical", safety_noted=True,
    )
    assert "final_urgency: RED" in red_prompt
    assert "safety_noted: true" in red_prompt        # bool은 소문자 json 형태로 주입됨
    assert "예약 권유 강도를 조절" in red_prompt
    assert "가장 빠른 예약" in red_prompt
    green_prompt = build_suspected_confirm_prompt("군밤이", "약간 기침", ["수의사 답변"])
    assert "final_urgency: GREEN" in green_prompt   # 기본값 GREEN 주입
