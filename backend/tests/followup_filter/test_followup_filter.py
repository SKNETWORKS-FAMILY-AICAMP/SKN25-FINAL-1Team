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


def _stub_vision(monkeypatch, findings: str = "", relevant=None) -> None:
    """첨부 분석(triage vision 재사용)을 스텁 — 테스트가 네트워크/VLM을 안 타게."""
    async def fake(_ctx, _msg):
        return findings, relevant

    monkeypatch.setattr(agent_mod, "analyze_media", fake)


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
    # 전화 없음 → '병원 연락'이 아니라 '더 빠른 예약(앞당김)'을 제안하는 문구가 붙어야 한다.
    assert ("빠른" in reply) or ("앞당" in reply)
    print("✓ urgent safety guidance (rebook offer) appended")


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
    _stub_vision(monkeypatch)
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
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("", attachments=["https://x/v.mp4"]), {}))
    assert len(calls) == 1
    assert calls[0]["ai_summary"] == "보호자가 상태 사진·영상을 공유함."
    assert res.events and res.events[0]["has_media"] is True
    print("✓ media-only saves with placeholder summary")


def test_vision_findings_enrich_reply_and_summary(monkeypatch):
    # 사진을 읽고(소견 있음) → 답변이 사진을 언급하고, 차트 요약에 소견이 들어가야 한다.
    _stub_vision(monkeypatch, findings="이미지 소견: 갈색 액상 토사물에 사료 알갱이 섞임", relevant=True)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "오늘 추가 구토",
                            "assistant_reply": "보내주신 사진 보니 사료가 덜 소화된 채 나온 것 같아요. "
                                               "수의사 선생님이 확인할 수 있게 남겨둘게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("또 토했어요", attachments=["https://x/v.jpg"]), {}))
    assert len(calls) == 1
    assert "사진 보니" in res.reply                       # 사진을 읽고 공감
    assert "토사물" in calls[0]["ai_summary"]             # 차트 요약에 소견 반영
    print("✓ vision findings enrich reply + chart summary")


def test_missent_photo_asks_and_does_not_save(monkeypatch):
    # 무관해 보이는 사진(relevant=false) + 텍스트도 경과 아님 → 저장하지 말고 되묻기.
    _stub_vision(monkeypatch, findings="이미지 소견: 사람 손/배경만 보임", relevant=False)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "혹시 이 사진이 뽀미 상태와 관련된 게 맞을까요? "
                                               "맞다면 한 번 더 보내주세요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("이거 봐바", attachments=["https://x/hand.jpg"]), {}))
    assert "맞을까요" in res.reply or "보내주세요" in res.reply   # 되묻기 노출
    assert len(calls) == 0                                        # ★ 잘못 보낸 사진은 저장 안 함
    assert res.events == []                                       # 저장 이벤트도 없음
    print("✓ mis-sent photo → ask & NOT saved")


def test_rebook_request_emits_event_and_no_save(monkeypatch):
    # "예약 바꾸고 싶어요" → 저장 없이 재예약 신호(rebook_request)만 내보낸다.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "wants_rebooking": True,
                            "assistant_reply": "네, 가능한 빠른 예약 시간을 찾아볼게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("예약 다른 날로 바꾸고 싶어요"), {}))
    assert len(calls) == 0                                       # 저장 안 함
    assert res.events and res.events[0]["type"] == "rebook_request"
    print("✓ rebook request → event, no save")


def test_rebook_pill_triggers_rebook(monkeypatch):
    # '더 빠른 시간 찾기' pill 클릭(결정론) → wants_rebooking 없어도 재예약 신호.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "wants_rebooking": False,
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("더 빠른 시간 찾기"), {}))
    assert res.events and res.events[0]["type"] == "rebook_request"
    assert len(calls) == 0
    print("✓ rebook pill → event")


def test_urgent_offers_rebook_pill(monkeypatch):
    # urgent 경과는 저장하되, 진료 앞당김 pill('더 빠른 시간 찾기')을 제안한다.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "urgent_possible", "summary_delta": "피 섞인 구토 반복",
                            "assistant_reply": "피가 섞여 나왔다니 많이 놀라셨겠어요. 남겨둘게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("피를 토했어요"), {}))
    assert len(calls) == 1                                       # urgent 경과는 저장
    assert "더 빠른 시간 찾기" in res.quick_replies              # 재예약 pill 제안
    print("✓ urgent → saved + rebook pill")


def test_relevant_photo_still_saves_even_if_text_not_followup(monkeypatch):
    # 사진이 증상과 관련됨(relevant=true)이면 텍스트가 경과 아니어도 저장(기존 보장 유지).
    _stub_vision(monkeypatch, findings="이미지 소견: 발적·진물 보이는 피부 병변", relevant=True)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "보내주신 사진 보니 피부가 붉고 진물이 보이네요. 남겨둘게요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("이거 봐바", attachments=["https://x/skin.jpg"]), {}))
    assert len(calls) == 1                                        # 관련 사진은 저장
    assert "피부" in calls[0]["ai_summary"] or "병변" in calls[0]["ai_summary"]
    print("✓ relevant photo → saved with vision summary")


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
