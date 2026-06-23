"""followup_filter 단위 테스트 - 경과 분류/저장 조건/안전 응답.

LLM/DB 실호출 없이(스텁) 분류·분기·저장조건만 고정한다.
pytest 없이도  python3 backend/tests/followup_filter/test_followup_filter.py  로 실행 가능.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import ai.agents.followup_filter.agent as agent_mod
import ai.agents.followup_filter.repository as repo_mod
from ai.agents.followup_filter.agent import followup_filter
from ai.agents.followup_filter.prompts import (
    HOSPITAL_INFO_PILL,
    NEW_BOOKING_DIRECT_PILL,
    PREP_INSTRUCTIONS_PILL,
    REBOOK_ACTION_PILL,
    REPLY_SAVED_VARIANTS,
    SCHEDULE_LIST_PILL,
    VISIT_NOTE_SUMMARY_PILL,
    pick_saved_reply,
)
from ai.agents.followup_filter.schema import (
    Category,
    allows_save_notice_question,
    ensure_safe_reply,
    keyword_fallback,
    merge_followup_summary,
    needs_saved_reply_fallback,
    parse_classification,
    strip_save_notice,
)
from ai.orchestrator.contracts import Intent, Phase, SessionContext
from app.utils.followup_policy import followup_cutoff_time, is_followup_open


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


def _stub_llm_sequence(monkeypatch, outs: list[dict]) -> None:
    queue = list(outs)

    async def fake(_prompt, temperature=0):
        if not queue:
            return outs[-1]
        return queue.pop(0)

    monkeypatch.setattr(agent_mod, "call_llm_json", fake)


def _stub_vision(monkeypatch, findings: str = "", relevant=None, species: str = "") -> None:
    """첨부 분석(triage vision 재사용)을 스텁 — 테스트가 네트워크/VLM을 안 타게."""
    async def fake(_ctx, _msg):
        return findings, relevant, species

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


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, value):
        self.value = value

    async def execute(self, _stmt):
        return _ScalarResult(self.value)

    def add(self, _obj):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


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


def test_followup_cutoff_boundaries_10_minutes():
    confirmed = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    assert followup_cutoff_time(confirmed) == confirmed - timedelta(minutes=10)
    assert is_followup_open(confirmed, now=confirmed - timedelta(minutes=11))
    assert not is_followup_open(confirmed, now=confirmed - timedelta(minutes=10))
    assert not is_followup_open(confirmed, now=confirmed - timedelta(minutes=9, seconds=59))
    assert not is_followup_open(confirmed, now=confirmed + timedelta(seconds=1))
    print("✓ followup cutoff boundaries: 11 open, 10/9:59/after-start limited")


def test_ensure_safe_reply_urgent_appends_guidance():
    cls = parse_classification(
        {"is_followup": True, "category": "stool_urine",
         "severity_hint": "urgent_possible", "summary_delta": "혈변",
         "assistant_reply": "걱정되시겠어요. 남겨둘게요."}, "피 섞인 설사")
    reply = ensure_safe_reply(cls, "fallback")
    # 전화 없음 → '병원 연락'이 아니라 '더 빠른 예약(앞당김)'을 제안하는 문구가 붙어야 한다.
    assert ("빠른" in reply) or ("앞당" in reply)
    print("✓ urgent safety guidance (rebook offer) appended")


def test_strip_save_notice_removes_only_save_sentence():
    reply = "수술 부위가 부어 보여 걱정되셨겠어요. 수의사 선생님이 확인할 수 있게 남겨둘게요."
    stripped = strip_save_notice(reply)
    assert "수의사 선생님이 확인할 수 있게" not in stripped
    assert "남겨둘게요" not in stripped
    assert stripped == "수술 부위가 부어 보여 걱정되셨겠어요."
    print("✓ strip_save_notice removes save notice sentence only")


def test_strip_save_notice_save_only_needs_fallback():
    reply = "말씀해주신 내용은 수의사 선생님이 확인할 수 있게 남겨둘게요."
    stripped = strip_save_notice(reply)
    assert needs_saved_reply_fallback(stripped, "수술 부위가 부었어요")
    fallback = REPLY_SAVED_VARIANTS[0]
    assert fallback
    assert not needs_saved_reply_fallback(fallback, "수술 부위가 부었어요")
    assert "기록" not in fallback and "전달" not in fallback and "남겨" not in fallback
    print("✓ save-notice-only reply falls back to non-save notice variant")


def test_strip_save_notice_allows_direct_record_question():
    user_message = "제가 말한 내용이 수의사 선생님께 전달되나요?"
    reply = "네, 말씀해주신 내용은 수의사 선생님께 전달됩니다."
    assert allows_save_notice_question(user_message)
    assert strip_save_notice(reply, allow_save_notice=allows_save_notice_question(user_message)) == reply
    assert len(reply) <= 40
    print("✓ direct record/delivery question allows short save notice")


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
    assert "남겨둘게요" not in res.reply
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
    assert "남겨둘게요" not in res.reply
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


def test_species_mismatch_asks_and_no_save(monkeypatch):
    # 등록 펫=고양이인데 사진=강아지(관련 있는 눈병이어도) → 잘못 보낸 사진으로 보고 저장 안 하고 확인.
    _stub_vision(monkeypatch, findings="이미지 소견: 한쪽 눈 충혈", relevant=True, species="dog")
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    # 실제 DB는 종을 한글('고양이')로 저장하기도 함 → 정규화해서 비교해야 잡힌다.
    ctx = SessionContext(
        session_id=1, userid=1, petid=1, pet_info={"name": "군밤", "species": "고양이"},
        hospitalid=1, emrid=16, scheduleid=None,
        user_message="어때보여?", attachments=["https://x/dog.jpg"],
        phase=Phase.BOOKED, db=object(),
    )
    res = _run(followup_filter.run(ctx, {}))
    assert "고양이" in res.reply and "강아지" in res.reply   # 종 불일치 안내
    assert len(calls) == 0                                   # 저장 안 함
    print("✓ species mismatch (KOREAN '고양이' pet / dog photo) → ask & NOT saved")


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
    assert "남겨둘게요" not in res.reply
    assert "피부" in calls[0]["ai_summary"] or "병변" in calls[0]["ai_summary"]
    print("✓ relevant photo → saved with vision summary")


def test_pick_saved_reply_deterministic_and_dedup():
    # 같은 입력이면 항상 같은 결과(결정론, 랜덤 X).
    assert pick_saved_reply(True, []) == pick_saved_reply(True, [])
    # 직전 봇 답변이 변형 중 하나와 같으면, 그 문장은 피해서 다른 변형을 고른다.
    history = [{"role": "assistant", "content": REPLY_SAVED_VARIANTS[0]}]
    picked = pick_saved_reply(True, history)
    assert picked in REPLY_SAVED_VARIANTS
    assert picked != REPLY_SAVED_VARIANTS[0]
    print("✓ pick_saved_reply deterministic + avoids repeating prev reply")


def test_saved_fallback_used_when_llm_reply_empty(monkeypatch):
    # assistant_reply가 비면 캔드 멘트로 떨어지되, 옛 고정문구가 아닌 변형 중 하나여야 한다.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "수술 부위 부종",
                            "assistant_reply": ""})
    _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("수술 부위가 조금 부어 있는 것 같아요"), {}))
    assert res.reply in REPLY_SAVED_VARIANTS                 # 변형 중 하나
    assert "수의사 선생님이 확인할 수 있게 남겨둘게요" not in res.reply
    print("✓ empty assistant_reply → saved-reply variant (not old fixed phrase)")


def test_saved_branch_replaces_save_notice_only_reply(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "수술 부위 부종",
                            "assistant_reply": "말씀해주신 내용은 수의사 선생님이 확인할 수 있게 남겨둘게요.",
                            "reply_kind": "stable_next", "asked_fields": []})
    _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("수술 부위가 조금 부어 있는 것 같아요"), {}))
    assert res.reply
    assert "수의사 선생님이 확인할 수 있게" not in res.reply
    assert "남겨둘게요" not in res.reply
    assert res.reply in REPLY_SAVED_VARIANTS
    print("✓ saved branch replaces save-notice-only LLM reply")


def test_saved_branch_allows_direct_delivery_question(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "other",
                            "severity_hint": "stable", "summary_delta": "보호자가 전달 여부를 문의함",
                            "assistant_reply": "네, 말씀해주신 내용은 수의사 선생님께 전달됩니다.",
                            "reply_kind": "stable_next", "asked_fields": []})
    _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("제가 말한 내용이 수의사 선생님께 전달되나요?"), {}))
    assert "전달" in res.reply
    assert len(res.reply) <= 40
    print("✓ saved branch allows short save notice for direct delivery question")


def test_five_turn_saved_reply_regression(monkeypatch):
    messages = [
        "수술 부위가 조금 부어 있는 것 같아요.",
        "밥을 평소보다 적게 먹네요.",
        "실밥 근처를 자꾸 핥으려고 해요.",
        "오늘은 좀 기운을 차린 것 같아요.",
        "그런데 한 번 토했어요.",
    ]
    llm_outs = [
        {"is_followup": True, "category": "symptom_change", "severity_hint": "worse",
         "summary_delta": "수술 부위 부종", "assistant_reply": "수술 부위가 부어 보여 걱정되셨겠어요. 수의사 선생님이 확인할 수 있게 남겨둘게요.",
         "reply_kind": "reflect_ask", "asked_fields": ["부종 변화"]},
        {"is_followup": True, "category": "appetite_energy", "severity_hint": "worse",
         "summary_delta": "식사량 감소", "assistant_reply": "밥을 적게 먹는 모습이 이어지는지 살펴봐 주세요. 기록해둘게요.",
         "reply_kind": "stable_next", "asked_fields": []},
        {"is_followup": True, "category": "pain_behavior", "severity_hint": "worse",
         "summary_delta": "실밥 주변 핥으려 함", "assistant_reply": "실밥 근처를 자꾸 핥으려는군요. 상처를 더 건드리는 모습이 있으면 이어서 알려주세요.",
         "reply_kind": "reflect_ask", "asked_fields": ["상처 건드림"]},
        {"is_followup": True, "category": "appetite_energy", "severity_hint": "stable",
         "summary_delta": "기운 호전", "assistant_reply": "오늘 기운을 조금 차린 것 같아 다행이에요. 식사량도 같이 돌아오는지 살펴봐 주세요.",
         "reply_kind": "stable_next", "asked_fields": []},
        {"is_followup": True, "category": "symptom_change", "severity_hint": "urgent_possible",
         "summary_delta": "구토 1회", "assistant_reply": "구토가 한 번 있었다니 걱정되셨겠어요. 수의사에게 전달해둘게요.",
         "reply_kind": "urgent_rebook", "asked_fields": []},
    ]
    _stub_vision(monkeypatch)
    _stub_llm_sequence(monkeypatch, llm_outs)
    calls = _stub_save(monkeypatch)

    history: list[dict] = []
    followup_summary = ""
    last_kind = ""
    asked_fields: list[str] = []
    diagnostics: list[dict] = []
    replies: list[str] = []

    forbidden_medical = ("진단", "처방", "용량", "병명", "정상입니다", "위험합니다", "괜찮습니다")
    save_notice_terms = ("기록해둘게요", "남겨둘게요", "정리해둘게요", "수의사 선생님이 확인할 수 있게", "수의사에게 전달", "진료 메모에 반영", "확인할 수 있도록 전달")

    for idx, message in enumerate(messages):
        raw = llm_outs[idx]["assistant_reply"]
        allow = allows_save_notice_question(message)
        stripped = strip_save_notice(ensure_safe_reply(parse_classification(llm_outs[idx], message), pick_saved_reply(True, history)),
                                     allow_save_notice=allow)
        ctx = _ctx(message)
        ctx.history = list(history)
        ctx.followup_summary = followup_summary
        ctx.last_followup_reply_kind = last_kind
        ctx.asked_followup_fields = list(asked_fields)
        res = _run(followup_filter.run(ctx, {}))
        replies.append(res.reply)
        history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": res.reply}])
        followup_summary = res.state_patch.get("followup_summary", followup_summary)
        last_kind = res.state_patch.get("last_followup_reply_kind", last_kind)
        asked_fields = res.state_patch.get("asked_followup_fields", asked_fields)

        assert res.reply
        assert res.state_patch.get("last_followup_reply_kind") == llm_outs[idx]["reply_kind"]
        for field in llm_outs[idx]["asked_fields"]:
            assert field in res.state_patch.get("asked_followup_fields", [])
        if llm_outs[idx]["severity_hint"] == "urgent_possible":
            assert "더 빠른 시간 찾기" in res.quick_replies
            assert ("빠른" in res.reply) or ("앞당" in res.reply)
        else:
            assert "더 빠른 시간 찾기" not in res.quick_replies
        assert not any(term in res.reply for term in forbidden_medical)

        diagnostics.append({
            "turn": idx + 1,
            "category": llm_outs[idx]["category"],
            "severity_hint": llm_outs[idx]["severity_hint"],
            "reply_kind": llm_outs[idx]["reply_kind"],
            "asked_fields": llm_outs[idx]["asked_fields"],
            "assistant_reply": raw,
            "strip_save_notice_applied": stripped != raw,
            "fallback_replaced": res.reply != stripped,
            "pass": True,
        })

    save_notice_hits = [any(term in r for term in save_notice_terms) for r in replies]
    assert not any(a and b for a, b in zip(save_notice_hits, save_notice_hits[1:]))
    assert len(calls) == 5
    for item in diagnostics:
        print(f"turn {item['turn']} diagnostics: {item}")
    print("✓ 5-turn saved reply regression")


def test_request_ending_not_repeated_for_five_followup_turns(monkeypatch):
    messages = [
        "피부가 더 빨개졌어요.",
        "진물이 조금 늘었어요.",
        "오늘도 비슷해요.",
        "긁는 건 줄었어요.",
        "밤에 또 핥으려고 했어요.",
    ]
    llm_outs = [
        {"is_followup": True, "category": "symptom_change", "severity_hint": "worse",
         "summary_delta": "피부 발적 증가", "assistant_reply": "피부가 더 붉어졌군요. 진물이 있는지도 알려주세요.",
         "reply_kind": "reflect_ask", "asked_fields": ["진물"]},
        {"is_followup": True, "category": "symptom_change", "severity_hint": "worse",
         "summary_delta": "진물 증가", "assistant_reply": "진물이 늘어난 부분이 있군요. 붉어진 범위도 함께 알려주세요.",
         "reply_kind": "reflect_ask", "asked_fields": ["발적 범위"]},
        {"is_followup": True, "category": "symptom_change", "severity_hint": "stable",
         "summary_delta": "상태 유사", "assistant_reply": "오늘도 비슷한 상태군요. 더 달라지는 부분이 있으면 알려주세요.",
         "reply_kind": "stable_next", "asked_fields": []},
        {"is_followup": True, "category": "pain_behavior", "severity_hint": "stable",
         "summary_delta": "긁음 감소", "assistant_reply": "긁는 모습이 줄었다면 그 흐름을 지켜봐 주세요.",
         "reply_kind": "stable_next", "asked_fields": []},
        {"is_followup": True, "category": "pain_behavior", "severity_hint": "worse",
         "summary_delta": "밤에 핥으려 함", "assistant_reply": "밤에 다시 핥으려 했군요. 상처를 건드리는지도 알려주세요.",
         "reply_kind": "reflect_ask", "asked_fields": ["상처 건드림"]},
    ]
    _stub_vision(monkeypatch)
    _stub_llm_sequence(monkeypatch, llm_outs)
    _stub_save(monkeypatch)

    history: list[dict] = []
    replies: list[str] = []
    endings: list[bool] = []
    for message in messages:
        ctx = _ctx(message)
        ctx.history = list(history)
        res = _run(followup_filter.run(ctx, {}))
        replies.append(res.reply)
        endings.append(res.reply.rstrip(".!?。！？").endswith(("알려주세요", "함께 알려주세요", "말씀해 주세요", "말씀해주세요")))
        history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": res.reply}])

    assert not any(a and b for a, b in zip(endings, endings[1:]))
    assert any(not r.endswith("?") for r in replies)
    assert not any(term in " ".join(replies) for term in ("진단", "처방", "용량", "정상입니다", "위험합니다"))
    print("✓ request-style endings do not repeat over 5 followup turns")


def test_pet_general_ecollar_reply_preserved(monkeypatch):
    # 넥카라 질문(pet_general) → LLM의 안전 안내문을 고정 fallback으로 덮어쓰지 않는다.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "pet_general",
                            "severity_hint": "stable", "summary_delta": "",
                            "assistant_reply": "수술 뒤 넥카라 필요 여부는 받으신 퇴원 안내가 있다면 "
                                               "그 지시를 우선 따라 주세요. 지금 상처를 자꾸 핥거나 "
                                               "건드리는 모습이 있으면 그 상태도 알려주세요."})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("넥카라를 꼭 해야 하나요?"), {}))
    assert len(calls) == 0                                   # 경과 아님 → 저장 안 함
    assert "퇴원 안내" in res.reply and "넥카라" in res.reply   # LLM 안내 그대로 유지
    print("✓ e-collar question → safe guidance preserved, not saved")


def test_new_booking_offers_choice_pills(monkeypatch):
    # "바로 예약할래"(신규) → 저장 없이 '바로 예약 / 문진 작성 후 예약' 선택지를 띄운다.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "wants_new_booking": True,
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("그냥 바로 예약할래"), {}))
    assert len(calls) == 0
    assert "새 예약하기" in res.quick_replies
    assert "문진 작성 후 예약하기" in res.quick_replies
    assert res.events == []                                  # 선택 전이라 동작 신호 없음
    print("✓ new booking → choice pills, no save")


def test_inchat_triage_pill_emits_event(monkeypatch):
    # '문진 작성 후 예약하기' pill(결정론) → start_inchat_triage 이벤트.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("문진 작성 후 예약하기"), {}))
    assert res.events and res.events[0]["type"] == "start_inchat_triage"
    assert len(calls) == 0
    print("✓ inchat-triage pill → event")


def test_schedule_list_emits_event(monkeypatch):
    # "예약 내역 보여줘" → list_schedules 이벤트(프론트가 목록 카드 렌더).
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_schedule_list": True,
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("내 예약 내역 보여줘"), {}))
    assert res.events and res.events[0]["type"] == "list_schedules"
    assert len(calls) == 0
    print("✓ schedule list → event")


def test_schedule_list_pill_emits_event(monkeypatch):
    # '예약 내역' pill(결정론) → wants 분류 없이도 list_schedules.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("예약 내역"), {}))
    assert res.events and res.events[0]["type"] == "list_schedules"
    assert len(calls) == 0
    print("✓ schedule-list pill → event")


def test_contextual_quick_replies_after_schedule_list(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_schedule_list": True,
                            "assistant_reply": ""})
    _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("예약 내역 볼래"), {}))
    assert [e["type"] for e in res.events] == ["list_schedules"]
    assert REBOOK_ACTION_PILL in res.quick_replies
    assert HOSPITAL_INFO_PILL in res.quick_replies
    assert NEW_BOOKING_DIRECT_PILL in res.quick_replies
    assert "상태 계속 알려주기" not in res.quick_replies
    print("✓ contextual quick replies after schedule list")


def test_contextual_quick_replies_after_saved_followup(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "피부 발적 증가",
                            "assistant_reply": "붉어지는 범위가 달라지는지 살펴봐 주세요.",
                            "reply_kind": "stable_next"})
    _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("피부가 더 빨개졌어요"), {}))
    assert "상태 계속 알려주기" in res.quick_replies
    assert REBOOK_ACTION_PILL in res.quick_replies
    assert SCHEDULE_LIST_PILL not in res.quick_replies
    print("✓ contextual quick replies after saved followup")


def test_limited_followup_message_not_saved(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "구토 1회",
                            "assistant_reply": "구토가 있었군요. 이어지는지 살펴봐 주세요.",
                            "reply_kind": "stable_next"})
    calls = _stub_save(monkeypatch)
    ctx = _ctx("방금 또 토했어요")
    ctx.followup_limited = True
    res = _run(followup_filter.run(ctx, {}))
    assert calls == []
    assert not any(e.get("type") == "followup_saved" for e in res.events)
    assert "전달되기 어려울 수" in res.reply
    assert REBOOK_ACTION_PILL not in res.quick_replies
    assert HOSPITAL_INFO_PILL in res.quick_replies
    assert SCHEDULE_LIST_PILL in res.quick_replies
    assert PREP_INSTRUCTIONS_PILL in res.quick_replies
    assert VISIT_NOTE_SUMMARY_PILL in res.quick_replies
    print("✓ limited followup message → chat reply only, no save")


def test_limited_followup_photo_not_saved(monkeypatch):
    _stub_vision(monkeypatch, findings="이미지 소견: 피부 발적", relevant=True)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse", "summary_delta": "피부 발적 사진",
                            "assistant_reply": "사진에서 붉어 보이는 부분이 있네요.",
                            "reply_kind": "stable_next"})
    calls = _stub_save(monkeypatch)
    ctx = _ctx("사진도 보낼게요", attachments=["https://x/skin.jpg"])
    ctx.followup_limited = True
    res = _run(followup_filter.run(ctx, {}))
    assert calls == []
    assert not any(e.get("type") == "followup_saved" for e in res.events)
    assert "전달되기 어려울 수" in res.reply
    print("✓ limited followup photo → no followupDB save")


def test_limited_rebook_and_cancel_blocked(monkeypatch):
    _stub_vision(monkeypatch)
    calls = _stub_save(monkeypatch)

    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "wants_rebooking": True,
                            "assistant_reply": "예약 변경을 도와드릴게요."})
    ctx = _ctx("예약 바꾸고 싶어요")
    ctx.followup_limited = True
    res = _run(followup_filter.run(ctx, {}))
    assert calls == []
    assert not any(e.get("type") == "rebook_request" for e in res.events)
    assert "앱에서 예약을 변경하거나 취소하기 어려워요" in res.reply
    assert REBOOK_ACTION_PILL not in res.quick_replies

    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "wants_cancel": True,
                            "assistant_reply": "예약 취소를 도와드릴게요."})
    ctx = _ctx("예약 취소하고 싶어요")
    ctx.followup_limited = True
    res = _run(followup_filter.run(ctx, {}))
    assert not any(e.get("type") == "cancel_request" for e in res.events)
    assert "앱에서 예약을 변경하거나 취소하기 어려워요" in res.reply
    print("✓ limited rebook/cancel → blocked without app events")


def test_limited_admin_queries_still_work(monkeypatch):
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_schedule_list": True,
                            "assistant_reply": ""})
    _stub_save(monkeypatch)
    ctx = _ctx("예약 내역 보여줘")
    ctx.followup_limited = True
    res = _run(followup_filter.run(ctx, {}))
    assert res.events and res.events[0]["type"] == "list_schedules"
    assert HOSPITAL_INFO_PILL in res.quick_replies
    assert REBOOK_ACTION_PILL not in res.quick_replies

    ctx = _ctx(HOSPITAL_INFO_PILL)
    ctx.followup_limited = True
    ctx.db = _FakeDb(None)
    res = _run(followup_filter.run(ctx, {}))
    assert "예약된 병원 정보" in res.reply
    assert HOSPITAL_INFO_PILL in res.quick_replies
    print("✓ limited admin queries → schedules/hospital info still work")


def test_followup_limit_notice_inserted_once_per_schedule():
    import os
    from types import SimpleNamespace

    os.environ["DEBUG"] = "false"
    from app.api.chat import _ensure_followup_limit_notice

    session = SimpleNamespace(messages=[], orch_state={})
    db = _FakeDb(None)
    schedule = SimpleNamespace(scheduleid=101)

    inserted = _run(_ensure_followup_limit_notice(db, session, schedule))
    assert inserted is True
    assert len(session.messages) == 1
    assert session.messages[0]["meta"]["type"] == "followup_limit_notice"
    assert session.orch_state["followup_limit_notice_scheduleid"] == "101"

    inserted = _run(_ensure_followup_limit_notice(db, session, schedule))
    assert inserted is False
    assert len(session.messages) == 1

    inserted = _run(_ensure_followup_limit_notice(db, session, SimpleNamespace(scheduleid=102)))
    assert inserted is True
    assert len(session.messages) == 2
    assert session.orch_state["followup_limit_notice_scheduleids"] == ["101", "102"]
    print("✓ followup limit notice inserted once per schedule")


def test_save_state_preserves_followup_limit_notice_marker():
    from types import SimpleNamespace

    import ai.orchestrator.state as state_mod

    session = SimpleNamespace(
        orch_state={
            "followup_limit_notice_scheduleid": "101",
            "followup_limit_notice_scheduleids": ["101"],
        }
    )
    ctx = _ctx("상태 알려줄게요")
    ctx.session = session
    ctx.followup_summary = "기존 요약"

    original_flag_modified = state_mod.flag_modified
    state_mod.flag_modified = lambda *_args, **_kwargs: None
    try:
        _run(state_mod.save_state(_FakeDb(None), ctx))
        assert session.orch_state["followup_limit_notice_scheduleid"] == "101"
        assert session.orch_state["followup_limit_notice_scheduleids"] == ["101"]
    finally:
        state_mod.flag_modified = original_flag_modified
    print("✓ save_state preserves followup limit notice marker")


def test_schedule_change_cancel_limited_boundary():
    import os
    from types import SimpleNamespace

    from fastapi import HTTPException

    os.environ["DEBUG"] = "false"
    import app.api.schedules as schedules_api

    now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    original_datetime = schedules_api.datetime

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    schedules_api.datetime = _FixedDateTime
    try:
        schedules_api._raise_if_booking_change_limited(
            SimpleNamespace(confirmed_time=now + timedelta(minutes=11))
        )
        for minutes in (10, 9):
            try:
                schedules_api._raise_if_booking_change_limited(
                    SimpleNamespace(confirmed_time=now + timedelta(minutes=minutes))
                )
            except HTTPException as exc:
                assert exc.status_code == 400
                assert "앱에서 예약을 변경하거나 취소하기 어려워요" in exc.detail
            else:
                raise AssertionError(f"{minutes} minutes before should be limited")
    finally:
        schedules_api.datetime = original_datetime
    print("✓ schedule change/cancel limited boundary")


def test_pending_hospital_info_confirmation(monkeypatch):
    class _Hospital:
        hospital_name = "MediPaw 동물병원"
        hospital_address = "서울시 강남구 테스트로 1"
        hospital_number = "02-0000-0001"

    ctx = _ctx("확인해줘")
    ctx.pending_confirmation_action = "hospital_info"
    ctx.db = _FakeDb(_Hospital())
    res = _run(followup_filter.run(ctx, {}))
    assert "MediPaw 동물병원" in res.reply
    assert "무엇을 확인" not in res.reply
    assert res.state_patch["pending_confirmation_action"] == ""
    assert SCHEDULE_LIST_PILL in res.quick_replies
    print("✓ pending hospital info + affirmative → direct lookup")


def test_pending_appointment_time_confirmation(monkeypatch):
    class _Schedule:
        confirmed_time = datetime(2026, 6, 23, 3, 30, tzinfo=timezone.utc)

    ctx = _ctx("응 보여줘")
    ctx.pending_confirmation_action = "appointment_time"
    ctx.db = _FakeDb(_Schedule())
    res = _run(followup_filter.run(ctx, {}))
    assert "예약 시간은" in res.reply
    assert "12:30" in res.reply
    assert "무엇을 확인" not in res.reply
    assert REBOOK_ACTION_PILL in res.quick_replies
    print("✓ pending appointment time + affirmative → confirmed_time")


def test_pending_schedule_list_confirmation(monkeypatch):
    ctx = _ctx("그래")
    ctx.pending_confirmation_action = "schedule_list"
    res = _run(followup_filter.run(ctx, {}))
    assert res.events and res.events[0]["type"] == "list_schedules"
    assert res.state_patch["pending_confirmation_action"] == ""
    print("✓ pending schedule-list + affirmative → list_schedules")


def test_pending_new_booking_confirmation(monkeypatch):
    ctx = _ctx("응")
    ctx.pending_confirmation_action = "new_booking"
    res = _run(followup_filter.run(ctx, {}))
    assert NEW_BOOKING_DIRECT_PILL in res.quick_replies
    assert "문진 작성 후 예약하기" in res.quick_replies
    assert res.state_patch["pending_confirmation_action"] == ""
    print("✓ pending new-booking + affirmative → booking choices")


def test_prep_instructions_emits_event(monkeypatch):
    # "준비사항 다시 알려줘" → show_prep 이벤트.
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_prep_instructions": True,
                            "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("내원 전 준비사항 다시 알려줘"), {}))
    assert res.events and res.events[0]["type"] == "show_prep"
    assert len(calls) == 0
    print("✓ prep instructions → event")


# --- 맥락 활용 회귀(A~D): 직전 대화·예약 컨텍스트·새 경과 반영 ---------------

def test_who_is_vet_uses_booking_context(monkeypatch):
    """A. "누구 의사지?" → 되묻기가 아니라 예약의 담당 수의사 이름을 안내한다."""
    class _VetRow:
        doctorid = 7
        doctor_name = "김민지"

    _stub_vision(monkeypatch)
    # LLM이 의도를 못 잡아도(other) 결정론 detection으로 수의사 조회로 가야 한다.
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    ctx = _ctx("누구 의사지?")
    ctx.db = _FakeDb(_VetRow())
    res = _run(followup_filter.run(ctx, {}))
    assert "김민지" in res.reply                         # 담당 수의사 실제 이름
    assert "무엇을 도와드릴까요" not in res.reply         # ★ 되묻기로 새 대화 시작 금지
    assert len(calls) == 0                               # 경과 아님 → 저장 안 함
    print("✓ A. '누구 의사지?' → 담당 수의사 안내(예약 컨텍스트 활용)")


def test_who_is_vet_via_llm_flag(monkeypatch):
    """A'. LLM이 asks_vet_info=true로 잡아도 동일하게 동작한다."""
    class _VetRow:
        doctorid = 7
        doctor_name = "이수의"

    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_vet_info": True,
                            "assistant_reply": ""})
    ctx = _ctx("이번에 누가 진료해요?")
    ctx.db = _FakeDb(_VetRow())
    res = _run(followup_filter.run(ctx, {}))
    assert "이수의" in res.reply
    print("✓ A'. asks_vet_info LLM 플래그 → 담당 수의사 안내")


def test_vet_subjective_question_gives_reassurance(monkeypatch):
    """유형4. "그 의사 친절해?" → 단정 없이 담당 이름 + 따뜻한 일반 안내(정보없음으로 안 끝남)."""
    class _VetRow:
        doctorid = 7
        doctor_name = "김민지"

    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "assistant_reply": ""})
    calls = _stub_save(monkeypatch)
    ctx = _ctx("그 의사 친절해?")
    ctx.db = _FakeDb(_VetRow())
    res = _run(followup_filter.run(ctx, {}))
    assert "김민지" in res.reply                          # 담당 이름 활용
    assert "노력하고 있어요" in res.reply                 # 주관 질문 → 일반 안내
    assert "무엇을 도와드릴까요" not in res.reply
    assert len(calls) == 0
    print("✓ 유형4. '그 의사 친절해?' → 이름 + 따뜻한 일반 안내")


def test_vet_info_no_data_still_reassures(monkeypatch):
    """유형4. 수의사 데이터가 없어도 '정보 없음'으로 끝내지 않고 일반 안내로 응답한다."""
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": False, "category": "other",
                            "severity_hint": "stable", "asks_vet_info": True,
                            "assistant_reply": ""})
    ctx = _ctx("누구 의사지?")
    ctx.db = _FakeDb(None)            # 조회 결과 없음
    res = _run(followup_filter.run(ctx, {}))
    assert "노력하고 있어요" in res.reply                 # 따뜻한 일반 안내로 마무리
    assert "정보가 없" not in res.reply and "확인하지 못" not in res.reply
    print("✓ 유형4. 수의사 데이터 없음 → 일반 안내(정보없음 종결 금지)")


def test_short_affirmatives_link_to_pending(monkeypatch):
    """P0. '그래'/'보여줘' 같은 짧은 응답이 직전 pending 액션으로 이어진다."""
    # '그래' → pending schedule_list 실행
    ctx = _ctx("그래")
    ctx.pending_confirmation_action = "schedule_list"
    res = _run(followup_filter.run(ctx, {}))
    assert res.events and res.events[0]["type"] == "list_schedules"
    # '보여줘' → pending appointment_time 실행
    class _Schedule:
        confirmed_time = datetime(2026, 6, 23, 3, 30, tzinfo=timezone.utc)
    ctx = _ctx("보여줘")
    ctx.pending_confirmation_action = "appointment_time"
    ctx.db = _FakeDb(_Schedule())
    res = _run(followup_filter.run(ctx, {}))
    assert "예약 시간은" in res.reply
    print("✓ P0. 짧은 응답('그래'/'보여줘')이 pending 액션으로 연결")


def test_photo_then_sudden_onset_reflected(monkeypatch):
    """B. (사진 직전) → "갑자기 생김" 이 답변에 반영되고, 관찰 안내만 반복하지 않는다."""
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "stable",
                            "summary_delta": "병변이 갑자기 발생했다고 보고",
                            "assistant_reply": "갑자기 생긴 거군요. 지금 모습이 더 달라지는지 알려주세요.",
                            "reply_kind": "reflect_ask", "asked_fields": ["변화"]})
    _stub_save(monkeypatch)
    # 직전 봇 답변이 요청형('알려주세요')으로 끝난 상황 — dedup이 답변을 통째로 갈아치우면 안 된다.
    ctx = _ctx("저게 왜 생긴 건지 모르겠네 갑자기 생김")
    ctx.history = [
        {"role": "user", "content": "(사진)"},
        {"role": "assistant", "content": "코 주변 붉은 자극이 보입니다. 가려운지, 긁는지 알려주세요."},
    ]
    res = _run(followup_filter.run(ctx, {}))
    assert "갑자기" in res.reply                          # ★ 새 경과 정보가 반영됨
    assert res.reply != "지금 보이는 모습이 더 달라지는지 지켜봐 주세요."  # 통째 교체 금지
    print("✓ B. 사진 뒤 '갑자기 생김' → 새 정보 반영(관찰 안내 반복 아님)")


def test_dedup_preserves_reflection_sentence():
    """B-unit: 직전도 요청형으로 끝나면 마지막 문장만 교체하고 되짚은 앞문장은 보존한다."""
    history = [{"role": "assistant", "content": "가려운지, 긁는지 알려주세요."}]
    out = agent_mod._avoid_consecutive_request_ending(
        "갑자기 생긴 거군요. 언제부터 그랬는지 알려주세요.", history)
    assert "갑자기 생긴 거군요" in out                    # 되짚은 앞문장 보존
    assert not out.rstrip(".!?。！？").endswith("알려주세요")  # 요청형 종결은 회피
    print("✓ B-unit. dedup이 되짚은 앞문장을 보존하고 종결만 교체")


def test_worse_change_reflected(monkeypatch):
    """C. "어제보다 심해짐" → 변화 정보가 반영된다(저장 + 답변)."""
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "symptom_change",
                            "severity_hint": "worse",
                            "summary_delta": "어제보다 증상 악화",
                            "assistant_reply": "어제보다 심해졌군요. 붉어진 범위가 더 넓어지는지 살펴봐 주세요.",
                            "reply_kind": "reflect_ask", "asked_fields": ["범위"]})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("어제보다 심해졌어요"), {}))
    assert len(calls) == 1
    assert "어제보다" in res.reply or "심해" in res.reply  # 변화 정보 반영
    assert "악화" in calls[0]["ai_summary"]               # 차트 요약에도 반영
    print("✓ C. '어제보다 심해짐' → 변화 정보 반영")


def test_medication_onset_reflected(monkeypatch):
    """D. "약 먹고 시작됨" → 약 관련 경과(medication_response)로 반영된다."""
    _stub_vision(monkeypatch)
    _stub_llm(monkeypatch, {"is_followup": True, "category": "medication_response",
                            "severity_hint": "worse",
                            "summary_delta": "처방약 복용 후 증상 시작",
                            "assistant_reply": "약을 드린 뒤부터 시작됐군요. 그 뒤로 구토나 처짐은 없는지 살펴봐 주세요.",
                            "reply_kind": "reflect_ask", "asked_fields": ["구토"]})
    calls = _stub_save(monkeypatch)
    res = _run(followup_filter.run(_ctx("약 먹고 나서 그래요"), {}))
    assert len(calls) == 1
    assert calls[0]["ai_summary"] and "약" in calls[0]["ai_summary"]  # 약 관련 경과로 저장
    assert "약" in res.reply                              # 답변에도 약 맥락 반영
    print("✓ D. '약 먹고 시작됨' → 약 관련 경과로 반영")


def test_pending_vet_info_confirmation(monkeypatch):
    """E. 수의사 안내 뒤 짧은 긍정('확인해줘')도 예약 컨텍스트로 이어진다."""
    class _VetRow:
        doctorid = 7
        doctor_name = "박수의"

    ctx = _ctx("확인해줘")
    ctx.pending_confirmation_action = "vet_info"
    ctx.db = _FakeDb(_VetRow())
    res = _run(followup_filter.run(ctx, {}))
    assert "박수의" in res.reply
    assert res.state_patch["pending_confirmation_action"] == ""
    print("✓ E. pending vet_info + 긍정 → 담당 수의사 직접 안내")


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
