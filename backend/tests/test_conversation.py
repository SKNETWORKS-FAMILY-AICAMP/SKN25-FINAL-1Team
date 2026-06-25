"""채팅 에이전트 공통 대화 헬퍼(ai.orchestrator.conversation) 단위 테스트.

A(포매터 통합)의 동작 불변과 B(durable 맥락 메모리)의 조합/의료안전을 고정한다.
LLM/DB 없이 순수 함수만 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.orchestrator.conversation import format_history, triage_context

_H = [
    {"role": "user", "content": "우리 강아지 토해요"},
    {"role": "assistant", "content": "언제부터요?"},
    {"role": "user", "content": "어제부터"},
]


def test_format_history_window_and_labels():
    # 최근 n턴만, 라벨은 호출자가 정한 대로.
    out = format_history(_H, 2, user_label="보호자", bot_label="봇")
    assert out == "봇: 언제부터요?\n보호자: 어제부터"


def test_format_history_default_role_labels():
    out = format_history(_H, 6)
    assert out == "user: 우리 강아지 토해요\nassistant: 언제부터요?\nuser: 어제부터"


def test_format_history_none_returns_all():
    assert len(format_history(_H, None).splitlines()) == 3


def test_format_history_empty_is_blank():
    assert format_history([]) == ""
    assert format_history(None) == ""


def test_format_history_skip_empty():
    h = [{"role": "user", "content": ""}, {"role": "assistant", "content": "안녕하세요"}]
    assert format_history(h, 6, skip_empty=True) == "assistant: 안녕하세요"
    # skip_empty=False면 빈 content 줄도 남는다(기존 reception/followup 동작).
    assert format_history(h, 6, skip_empty=False) == "user: \nassistant: 안녕하세요"


def _triage_state(chief=None, suspected=None, summary=""):
    return {"last_complete": {"data": {
        "chief_complaints": chief or [],
        "suspected_conditions": suspected or [],
        "triage_summary": summary,
    }}}


def test_triage_context_composes_chief_and_summary():
    mem = triage_context(_triage_state(chief=["구토", "설사"], summary="어제부터 구토"))
    assert "주증상: 구토, 설사" in mem
    assert "어제부터 구토" in mem
    assert mem.startswith("[지난 문진 맥락")


def test_triage_context_excludes_suspected_conditions():
    # ★ 의료 안전: 의심질환은 진단 단정을 유발할 수 있어 다운스트림 맥락에 넣지 않는다.
    mem = triage_context(_triage_state(chief=["구토"], suspected=["췌장염"], summary="구토"))
    assert "췌장염" not in mem
    assert "진단·처방 단정 금지" in mem


def test_triage_context_empty_when_no_data():
    assert triage_context({}) == ""
    assert triage_context(None) == ""
    assert triage_context(_triage_state()) == ""


def test_triage_context_partial_only_summary():
    mem = triage_context(_triage_state(summary="어제부터 기침"))
    assert "문진 요약: 어제부터 기침" in mem
    assert "주증상" not in mem


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("\n전부 통과 ✅")
