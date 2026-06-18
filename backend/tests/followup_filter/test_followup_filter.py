"""followup_filter 단위 테스트 - 경과 분류/저장 조건/안전 응답.

LLM/DB 실호출 없이(스텁) 분류·분기·저장조건만 고정한다.
pytest 없이도  python3 backend/tests/followup_filter/test_followup_filter.py  로 실행 가능.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import ai.agents.followup_filter.agent as agent_mod
import ai.agents.followup_filter.repository as repo_mod
from ai.agents.followup_filter.agent import followup_filter
from ai.agents.followup_filter.schema import (
    Category,
    ensure_safe_reply,
    keyword_fallback,
    merge_followup_summary,
    parse_classification,
)
from ai.orchestrator.contracts import Intent, Phase, SessionContext


def _ctx(message: str = "", attachments: list[str] | None = None,
         emrid: int | None = 16) -> SessionContext:
    return SessionContext(
        session_id=1, userid=1, petid=1, pet_info={"name": "테스트펫"},
        hospitalid=1, emrid=emrid, scheduleid=None,
        user_message=message, attachments=attachments or [],
        phase=Phase.BOOKED, db=object(),
    )


def _run(awaitable):
    return asyncio.run(awaitable)


def _stub_llm(monkeypatch, out: dict) -> None:
    async def fake(_prompt, temperature=0):
        return out

    monkeypatch.setattr(agent_mod, "call_llm_json", fake)


def _stub_save(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    class _Row:
        followupid = 999

    async def fake(db, **kw):
        calls.append(kw)
        return _Row()

    monkeypatch.setattr(repo_mod, "save_followup", fake)
    return calls


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


# --- 동기 유닛: 스키마 / 머지 / 안전응답 -------------------------------------

def test_parse_symptom_change():
    cls = parse_classification(
        {"is_followup": True, "category": "symptom_change",
         "severity_hint": "worse", "summary_delta": "구토 3회"}, "오늘 구토 3번")
    assert cls.is_followup
    assert cls.category == Category.SYMPTOM_CHANGE
    print("✓ parse symptom_change")


def test_parse_non_followup_clears_summary():
    cls = parse_classification(
        {"is_followup": False, "category": "pet_general",
         "summary_delta": "남으면안됨"}, "비타민 먹여도 돼요?")
    assert not cls.is_followup
    assert cls.summary_delta == ""   # 경과 아니면 비움
    print("✓ non-followup clears summary_delta")


def test_keyword_fallback():
    assert keyword_fallback("오늘 구토를 3번 더 했어요").is_followup
    assert keyword_fallback("병원 주소가 어디예요?").category == Category.HOSPITAL_INFO
    assert keyword_fallback("파이썬 코드 짜줘").category == Category.IRRELEVANT
    print("✓ keyword fallback")


def test_merge_summary():
    assert merge_followup_summary("", "구토 3회") == "구토 3회"
    assert merge_followup_summary("구토 3회", "설사 감소") == "구토 3회 / 설사 감소"
    assert merge_followup_summary("기존", "") == "기존"
    print("✓ merge summary")


def test_ensure_safe_reply_urgent_appends_guidance():
    cls = parse_classification(
        {"is_followup": True, "category": "stool_urine",
         "severity_hint": "urgent_possible", "summary_delta": "혈변",
         "assistant_reply": "걱정되시겠어요. 남겨둘게요."}, "피 섞인 설사")
    reply = ensure_safe_reply(cls, "fallback")
    assert "병원" in reply   # 응급인데 안내 없으면 코드가 보정
    print("✓ urgent safety guidance appended")


# --- 비동기: agent.run 분기 -------------------------------------------------

def test_symptom_saved(monkeypatch):
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "구토 3회 추가",
                            "assistant_reply": "걱정되시겠어요. 남겨둘게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("오늘 구토를 3번 더 했어요"), {}))
    assert len(calls) == 1
    assert calls[0]["message"] == "오늘 구토를 3번 더 했어요"
    assert calls[0]["ai_summary"] == "구토 3회 추가"
    assert calls[0]["emergency_alert"] is False
    assert res.events and res.events[0]["type"] == "followup_saved"
    print("✓ symptom → saved")


def test_hospital_info_not_saved_and_handoff(monkeypatch):
    _stub_llm(monkeypatch, {"is_followup": False, "category": "hospital_info",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "안내 담당이 도와드릴게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("병원 몇 시까지 해요?"), {}))
    assert len(calls) == 0
    assert res.handoff == Intent.RECEPTION
    print("✓ hospital_info → not saved, handoff reception")


def test_irrelevant_not_saved(monkeypatch):
    _stub_llm(monkeypatch, {"is_followup": False, "category": "irrelevant",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "상태 변화 있으면 알려주세요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("내일 날씨 어때?"), {}))
    assert len(calls) == 0
    assert res.events == []
    print("✓ irrelevant → not saved")


def test_media_forces_save_even_if_not_followup(monkeypatch):
    _stub_llm(monkeypatch, {"is_followup": False, "category": "pet_general",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "안내 담당이 도와드릴게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(
        _ctx("아이가 기운이 없는걸까?", attachments=["https://x/cat.jpg"]), {}))
    assert len(calls) == 1
    assert calls[0]["images"] == ["https://x/cat.jpg"]
    assert res.events and res.events[0]["forced_by_media"] is True
    print("✓ media forces save")


def test_media_only_no_text_uses_placeholder(monkeypatch):
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("", attachments=["https://x/v.mp4"]), {}))
    assert len(calls) == 1
    assert calls[0]["ai_summary"] == "보호자가 상태 사진·영상을 공유함."
    assert res.events and res.events[0]["has_media"] is True
    print("✓ media-only saves with placeholder summary")


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
