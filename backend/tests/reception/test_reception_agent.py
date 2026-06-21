"""응대 에이전트 단위 테스트 - 응답 조립·마무리 보정·스트릭 추적.

LLM/DB 실호출 없이(스텁) 분기·조합·안전 보정만 고정한다.
pytest 없이도  python3 backend/tests/reception/test_reception_agent.py  로 실행 가능.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import ai.agents.reception.agent as agent_mod
from ai.agents.reception.agent import _hospital_facts, _prev_was_vet_intro, reception
from ai.orchestrator.contracts import Phase, SessionContext


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _ctx(
    message: str = "안녕하세요",
    hospitalid: int | None = 1,
    history: list[dict] | None = None,
    reception_streak: int = 0,
) -> SessionContext:
    return SessionContext(
        session_id=1, userid=1, petid=1,
        pet_info={"name": "초코"},
        hospitalid=hospitalid,
        emrid=None, scheduleid=None,
        user_message=message,
        phase=Phase.PRE_BOOKING,
        db=object(),
        history=history or [],
        reception_streak=reception_streak,
    )


def _run(coro):
    return asyncio.run(coro)


def _stub_llm(monkeypatch, out: dict) -> None:
    async def fake(_prompt, **_kw):
        return out
    monkeypatch.setattr(agent_mod, "call_llm_json", fake)


def _stub_facts(monkeypatch, result: str = "병원명: 테스트병원") -> None:
    async def fake(_db, _hospitalid, _question, history=None):
        return result
    monkeypatch.setattr(agent_mod, "_hospital_facts", fake)


class _MiniMonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name: str, value) -> None:
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self) -> None:
        for obj, name, old_value in reversed(self._undo):
            setattr(obj, name, old_value)
        self._undo.clear()


# ── Group 1: _prev_was_vet_intro() 순수 함수 ─────────────────────────────────

def test_prev_vet_intro_true():
    history = [{"role": "assistant", "content": "저희 병원에는 수의사 선생님이 계세요!"}]
    assert _prev_was_vet_intro(history) is True
    print("✓ 수의사 언급 → True")


def test_prev_vet_intro_no_assistant():
    history = [{"role": "user", "content": "수의사 소개 부탁드려요"}]
    assert _prev_was_vet_intro(history) is False
    print("✓ user 메시지만 있음 → False")


def test_prev_vet_intro_empty():
    assert _prev_was_vet_intro([]) is False
    assert _prev_was_vet_intro(None) is False
    print("✓ 빈 이력 → False")


def test_prev_vet_intro_non_vet():
    history = [{"role": "assistant", "content": "운영시간은 09:00~18:00입니다."}]
    assert _prev_was_vet_intro(history) is False
    print("✓ 수의사 무관 assistant 메시지 → False")


# ── Group 2: _hospital_facts() 조기 종료 ─────────────────────────────────────

def test_facts_no_db():
    result = _run(_hospital_facts(None, 1, "주소 알려주세요"))
    assert result == "등록된 병원 정보가 없습니다."
    print("✓ db=None → 오류 문자열")


def test_facts_no_hospitalid():
    result = _run(_hospital_facts(object(), None, "주소 알려주세요"))
    assert result == "등록된 병원 정보가 없습니다."
    print("✓ hospitalid=None → 오류 문자열")


# ── Group 3: ReceptionAgent.run() 응답 조립 ──────────────────────────────────

def test_run_normal_reply(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {"reply": "병원 주소는 서울시 강남구입니다. 또 궁금한 점 있으신가요?", "pills": ["운영시간", "수의사 소개"]})
    res = _run(reception.run(_ctx("주소 알려주세요"), {}))
    assert "강남구" in res.reply
    assert res.quick_replies == ["운영시간", "수의사 소개"]
    print("✓ 정상 응답 — reply + quick_replies")


def test_run_streak_from_zero(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {"reply": "안내 드릴게요. 또 궁금한 점 있으신가요?", "pills": []})
    res = _run(reception.run(_ctx(reception_streak=0), {}))
    assert res.state_patch == {"reception_streak": 1}
    print("✓ reception_streak=0 → state_patch 1")


def test_run_streak_from_existing(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {"reply": "안내 드릴게요. 또 궁금한 점 있으신가요?", "pills": []})
    res = _run(reception.run(_ctx(reception_streak=3), {}))
    assert res.state_patch == {"reception_streak": 4}
    print("✓ reception_streak=3 → state_patch 4")


def test_run_llm_exception_fallback(monkeypatch):
    _stub_facts(monkeypatch)

    async def boom(_prompt, **_kw):
        raise RuntimeError("LLM 오류")

    monkeypatch.setattr(agent_mod, "call_llm_json", boom)
    res = _run(reception.run(_ctx(), {}))
    assert "문의" in res.reply or "다시 시도" in res.reply
    assert res.quick_replies == []
    print("✓ LLM 예외 → 폴백 메시지")


def test_run_closing_appended(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {"reply": "병원 주소는 서울시 강남구입니다.", "pills": []})
    res = _run(reception.run(_ctx(), {}))
    last_line = res.reply.rstrip().split("\n")[-1]
    closing_kw = ("말씀해 주세요", "있으신가요", "도와드릴까요", "알려주세요",
                  "찾아주세요", "연락주세요", "궁금한 점", "궁금한 게")
    has_closing = last_line.endswith("?") or any(k in last_line for k in closing_kw)
    assert has_closing, f"마무리 문장이 없음: '{last_line}'"
    print("✓ 마무리 없는 reply → 자동 추가")


def test_run_closing_not_duplicated(monkeypatch):
    _stub_facts(monkeypatch)
    original = "병원 주소는 서울시 강남구입니다. 또 궁금한 점 있으신가요?"
    _stub_llm(monkeypatch, {"reply": original, "pills": []})
    res = _run(reception.run(_ctx(), {}))
    count = res.reply.count("궁금한 점")
    assert count == 1, f"마무리 문장이 중복됨 (count={count})"
    print("✓ 이미 물음표 마무리 → 중복 추가 안 함")


def test_run_closing_keyword_present(monkeypatch):
    _stub_facts(monkeypatch)
    original = "운영시간은 09:00~18:00이에요. 더 필요한 정보 있으신가요?"
    _stub_llm(monkeypatch, {"reply": original, "pills": []})
    res = _run(reception.run(_ctx(), {}))
    assert res.reply.count("있으신가요") == 1
    print("✓ 클로징 키워드 이미 있음 → 추가 안 함")


def test_run_pills_capped_at_4(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {
        "reply": "안내 드릴게요. 또 궁금한 점 있으신가요?",
        "pills": ["병원 위치", "운영시간", "수의사 소개", "예약하기", "전화번호"],
    })
    res = _run(reception.run(_ctx(), {}))
    assert len(res.quick_replies) == 4
    print("✓ pills 5개 → 4개로 제한")


def test_run_empty_pills_filtered(monkeypatch):
    _stub_facts(monkeypatch)
    _stub_llm(monkeypatch, {
        "reply": "안내 드릴게요. 또 궁금한 점 있으신가요?",
        "pills": ["버튼", "", "  "],
    })
    res = _run(reception.run(_ctx(), {}))
    assert res.quick_replies == ["버튼"]
    print("✓ 빈 string pills 필터링")


# ── __main__ (pytest 없이 직접 실행) ─────────────────────────────────────────

if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            if _fn.__code__.co_argcount:
                _mp = _MiniMonkeyPatch()
                try:
                    _fn(_mp)
                finally:
                    _mp.undo()
            else:
                _fn()
    print("\n전부 통과 ✅")
