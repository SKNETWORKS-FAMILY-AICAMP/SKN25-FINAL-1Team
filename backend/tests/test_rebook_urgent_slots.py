"""재예약(rebook) 슬롯의 '긴급 경과 우선' 로직 검증.

DB 없이 순수 헬퍼만 검증한다(_is_recent_emergency / _apply_urgent_slot_priority).
실제 슬롯 계산(recommend_slots)은 backend/tests/test_recommend_slots.py가 따로 본다.
pytest 없이도  python3 backend/tests/test_rebook_urgent_slots.py  로 실행 가능.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.followup import _apply_urgent_slot_priority, _is_recent_emergency


# ── _is_recent_emergency: '직전 followup 1건 + 최근 24h' 게이트 ───────────────
def test_recent_emergency_within_24h_is_true():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    created = now - timedelta(hours=2)
    assert _is_recent_emergency(True, created, now=now) is True


def test_old_emergency_beyond_24h_is_false():
    # P0-4. 24h를 넘긴 응급 경과는 이후 일반 예약 변경에 반영되지 않는다.
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    created = now - timedelta(hours=25)
    assert _is_recent_emergency(True, created, now=now) is False


def test_non_emergency_is_false():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    assert _is_recent_emergency(False, now - timedelta(minutes=1), now=now) is False
    assert _is_recent_emergency(None, now, now=now) is False
    assert _is_recent_emergency(True, None, now=now) is False


def test_naive_created_at_treated_as_utc():
    # created_at이 tz 없이 와도(naive) UTC로 보고 비교가 깨지지 않는다.
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 6, 24, 11, 0)  # tzinfo 없음
    assert _is_recent_emergency(True, naive, now=now) is True


# ── _apply_urgent_slot_priority: 긴급이면 earliest를 recommended로 끌어올림 ──
def _recs():
    return {
        "bucket": "normal",
        "recommended": [{"date": "2026-06-26", "start_time": "10:00"}],
        "earliest": [{"date": "2026-06-24", "start_time": "09:00"}],
        "by_doctor": {},
    }


def test_urgent_promotes_earliest_to_recommended():
    # P0-3. 긴급이면 가장 빠른 슬롯(earliest)이 기본 추천 자리로 올라온다.
    out = _apply_urgent_slot_priority(_recs(), urgent=True)
    assert out["recommended"] == out["earliest"]
    assert out["recommended"][0]["date"] == "2026-06-24"
    assert out["urgent"] is True
    assert out["earliest"] == _recs()["earliest"]  # earliest는 보존


def test_non_urgent_keeps_recommended():
    # P0-5. 일반 재예약은 기존 추천 그대로(회귀 없음).
    out = _apply_urgent_slot_priority(_recs(), urgent=False)
    assert out["recommended"][0]["date"] == "2026-06-26"
    assert "urgent" not in out


def test_urgent_without_earliest_is_noop():
    recs = {"bucket": "normal", "recommended": [{"date": "2026-06-26"}], "earliest": [], "by_doctor": {}}
    out = _apply_urgent_slot_priority(recs, urgent=True)
    assert out["recommended"][0]["date"] == "2026-06-26"  # earliest 없으면 그대로


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("\n전부 통과 ✅")
