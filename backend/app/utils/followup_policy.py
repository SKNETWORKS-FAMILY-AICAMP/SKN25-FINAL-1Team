from __future__ import annotations

from datetime import datetime, timedelta, timezone


FOLLOWUP_CLOSE_BEFORE_MINUTES = 10
FOLLOWUP_LIMIT_NOTICE_TYPE = "followup_limit_notice"
FOLLOWUP_LIMITED_REPLY = (
    "지금 보내주신 내용은 이번 예약 진료에 바로 전달되기 어려울 수 있어요. "
    "진료 때 수의사 선생님께도 함께 말씀해 주세요."
)
FOLLOWUP_LIMIT_NOTICE = (
    "진료 시작 10분 전부터는 새로 보내주시는 상태나 사진이 이번 예약 진료에 전달되지 않을 수 있어요. "
    "채팅으로 병원 정보와 예약 내용을 계속 확인하실 수 있어요."
)
BOOKING_CHANGE_LIMITED_REPLY = (
    "진료 시작 시간이 가까워 앱에서 예약을 변경하거나 취소하기 어려워요. "
    "병원에 직접 확인해 주세요."
)


def ensure_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def followup_cutoff_time(confirmed_time: datetime) -> datetime:
    return ensure_utc(confirmed_time) - timedelta(minutes=FOLLOWUP_CLOSE_BEFORE_MINUTES)


def is_followup_open(confirmed_time: datetime, *, now: datetime | None = None) -> bool:
    current = ensure_utc(now or datetime.now(timezone.utc))
    return current < followup_cutoff_time(confirmed_time)


def is_followup_limited(confirmed_time: datetime, *, now: datetime | None = None) -> bool:
    return not is_followup_open(confirmed_time, now=now)
