"""recommend_slots 검증: 3버킷 통일 / 모드별 3개 제한 / 의사 골고루 분산.

DB 없이 app.crud.schedule.get_available_slots 를 스텁해 결정론 로직만 검증한다.
"""
import asyncio

import pytest

import app.crud.schedule as sched
from app.crud.schedule import (
    AvailableSlot,
    _BUCKET_DAY_QUOTAS,
    _pick_diverse,
    _recommend_bucket,
    recommend_slots,
)


# ── 1. 3버킷 통일 ──────────────────────────────────────────────
@pytest.mark.parametrize("urgency,expected", [
    ("RED", "emergency"), ("ORANGE", "semi"),
    ("YELLOW", "normal"), ("GREEN", "normal"),
    (1, "emergency"), (2, "semi"), (3, "normal"), (4, "normal"),
])
def test_bucket_3way(urgency, expected):
    assert _recommend_bucket(urgency) == expected


def test_quota_sums_to_3():
    # 모든 버킷은 정확히 3개를 추천해야 한다(탭별 3개 제한).
    for bucket, quota in _BUCKET_DAY_QUOTAS.items():
        assert sum(quota) == 3, f"{bucket} quota {quota} != 3"
    assert _BUCKET_DAY_QUOTAS["emergency"] == [2, 1]
    assert _BUCKET_DAY_QUOTAS["semi"] == [1, 2]
    assert _BUCKET_DAY_QUOTAS["normal"] == [1, 1, 1]


# ── 2. _pick_diverse: 의사 골고루 ──────────────────────────────
def _slot(t, doc):
    return AvailableSlot(start_time=t, end_time=t, doctorid=doc, doctor_name=f"d{doc}")


def test_pick_diverse_spreads_doctors():
    # doc1이 이른 슬롯을 독식해도, 2개 뽑을 땐 doc1·doc2가 섞여야 한다.
    slots = [_slot("09:00", 1), _slot("09:30", 1), _slot("10:00", 2)]
    used: dict[int, int] = {}
    picked = _pick_diverse(slots, 2, used)
    assert {s.doctorid for s in picked} == {1, 2}


def test_pick_diverse_falls_back_when_single_doctor():
    # 한 의사밖에 없으면 어쩔 수 없이 그 의사로 채운다(쩔수).
    slots = [_slot("09:00", 1), _slot("09:30", 1)]
    picked = _pick_diverse(slots, 2, {})
    assert [s.doctorid for s in picked] == [1, 1]


# ── 3. recommend_slots end-to-end (get_available_slots 스텁) ────
def _make_stub():
    """날짜별 슬롯 공급: day0 = doc1 3개 + doc2 2개, 그 외 날 = doc1·doc2 각 1개."""
    from datetime import datetime
    from app.utils.timezone import KST
    today = datetime.now(KST).date().isoformat()

    async def fake_get_available_slots(db, date, duration_min, doctorid=None, hospitalid=None):
        if date == today:
            slots = [
                _slot("09:00", 1), _slot("09:30", 1), _slot("10:00", 1),
                _slot("11:00", 2), _slot("11:30", 2),
            ]
        else:
            slots = [_slot("09:00", 1), _slot("14:00", 2)]
        if doctorid is not None:
            slots = [s for s in slots if s.doctorid == doctorid]
        slots.sort(key=lambda s: (s.start_time, s.doctorid))
        return slots, ""
    return fake_get_available_slots


def _run(urgency):
    return asyncio.run(
        recommend_slots(db=None, urgency=urgency, duration_min=30, hospitalid=None, doctorid=None)
    )


def test_recommended_caps_at_3_all_buckets(monkeypatch):
    monkeypatch.setattr(sched, "get_available_slots", _make_stub())
    for urgency in ("RED", "ORANGE", "GREEN"):
        rec = _run(urgency)
        assert len(rec["recommended"]) == 3, f"{urgency} recommended != 3"
        assert len(rec["earliest"]) == 3, f"{urgency} earliest != 3"


def test_recommended_mixes_doctors(monkeypatch):
    monkeypatch.setattr(sched, "get_available_slots", _make_stub())
    rec = _run("GREEN")  # normal [1,1,1]
    docs = {s["doctorid"] for s in rec["recommended"]}
    assert docs == {1, 2}, f"한 의사만 떴다: {rec['recommended']}"


def test_emergency_first_day_is_diverse(monkeypatch):
    monkeypatch.setattr(sched, "get_available_slots", _make_stub())
    rec = _run("RED")  # emergency [2,1] → 첫날 2개는 의사 섞임
    first_day = [s for s in rec["recommended"] if s["date"] == rec["recommended"][0]["date"]]
    # 첫날 2개 슬롯의 의사가 서로 다름
    assert len({s["doctorid"] for s in first_day[:2]}) == 2
