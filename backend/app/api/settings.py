from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.schedule import Schedule
from app.models.vet_schedule import VetSchedule

router = APIRouter(prefix="/doctor/settings", tags=["doctor-settings"])

_DEFAULT_WEEK = [
    {"day_of_week": 0, "is_open": True,  "start_time": "09:00", "end_time": "18:00", "lunch_start": "12:00", "lunch_end": "13:00"},
    {"day_of_week": 1, "is_open": True,  "start_time": "09:00", "end_time": "18:00", "lunch_start": "12:00", "lunch_end": "13:00"},
    {"day_of_week": 2, "is_open": True,  "start_time": "09:00", "end_time": "18:00", "lunch_start": "12:00", "lunch_end": "13:00"},
    {"day_of_week": 3, "is_open": True,  "start_time": "09:00", "end_time": "18:00", "lunch_start": "12:00", "lunch_end": "13:00"},
    {"day_of_week": 4, "is_open": True,  "start_time": "09:00", "end_time": "18:00", "lunch_start": "12:00", "lunch_end": "13:00"},
    {"day_of_week": 5, "is_open": False, "start_time": None,    "end_time": None,    "lunch_start": None,    "lunch_end": None},
    {"day_of_week": 6, "is_open": False, "start_time": None,    "end_time": None,    "lunch_start": None,    "lunch_end": None},
]


# ── 스키마 ──────────────────────────────────────────────────────────────

class OperatingHoursResponse(BaseModel):
    start_time: str
    end_time: str
    lunch_start: str
    lunch_end: str


class OperatingHoursRequest(BaseModel):
    start_time: str
    end_time: str
    lunch_start: str
    lunch_end: str


class DaySchedule(BaseModel):
    day_of_week: int
    is_open: bool
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None


class WeeklyScheduleResponse(BaseModel):
    schedule: list[DaySchedule]


class ClosedDatesResponse(BaseModel):
    dates: list[str]


class AddClosedDateRequest(BaseModel):
    date: str


class AddClosedDateResponse(BaseModel):
    success: bool
    has_existing_reservations: bool
    reservation_count: int


# ── 유틸 ────────────────────────────────────────────────────────────────

def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _fmt(t: Optional[time]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


# ── 기존 운영시간 (하위 호환) ────────────────────────────────────────────

@router.get("/operating-hours", response_model=OperatingHoursResponse)
async def get_operating_hours(
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    # 주간 템플릿 중 첫 번째 영업 요일 기준 반환
    result = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.day_of_week.isnot(None),
            VetSchedule.is_open == True,
        )
        .order_by(VetSchedule.day_of_week)
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record and record.start_time:
        return OperatingHoursResponse(
            start_time=record.start_time.strftime("%H:%M"),
            end_time=record.end_time.strftime("%H:%M"),
            lunch_start=record.lunch_start.strftime("%H:%M") if record.lunch_start else "12:00",
            lunch_end=record.lunch_end.strftime("%H:%M") if record.lunch_end else "13:00",
        )
    # 주간 템플릿 없으면 date 기반 레코드 fallback
    result2 = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.date.isnot(None),
            VetSchedule.start_time.isnot(None),
        )
        .order_by(VetSchedule.date.desc())
        .limit(1)
    )
    record2 = result2.scalar_one_or_none()
    if record2:
        return OperatingHoursResponse(
            start_time=record2.start_time.strftime("%H:%M"),
            end_time=record2.end_time.strftime("%H:%M"),
            lunch_start=record2.lunch_start.strftime("%H:%M") if record2.lunch_start else "12:00",
            lunch_end=record2.lunch_end.strftime("%H:%M") if record2.lunch_end else "13:00",
        )
    return OperatingHoursResponse(start_time="09:00", end_time="18:00", lunch_start="12:00", lunch_end="13:00")


@router.put("/operating-hours", response_model=OperatingHoursResponse)
async def update_operating_hours(
    body: OperatingHoursRequest,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    # 월~금 주간 템플릿에 동일 시간 적용
    for dow in range(5):
        result = await db.execute(
            select(VetSchedule).where(
                VetSchedule.doctorid == current_doctor.doctorid,
                VetSchedule.day_of_week == dow,
            )
        )
        record = result.scalar_one_or_none()
        if record:
            record.is_open = True
            record.start_time = _parse_time(body.start_time)
            record.end_time = _parse_time(body.end_time)
            record.lunch_start = _parse_time(body.lunch_start)
            record.lunch_end = _parse_time(body.lunch_end)
        else:
            db.add(VetSchedule(
                doctorid=current_doctor.doctorid,
                day_of_week=dow,
                is_open=True,
                start_time=_parse_time(body.start_time),
                end_time=_parse_time(body.end_time),
                lunch_start=_parse_time(body.lunch_start),
                lunch_end=_parse_time(body.lunch_end),
            ))
    await db.commit()
    return OperatingHoursResponse(**body.model_dump())


# ── 주간 스케줄 ──────────────────────────────────────────────────────────

@router.get("/weekly-schedule", response_model=WeeklyScheduleResponse)
async def get_weekly_schedule(
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    result = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.day_of_week.isnot(None),
        )
        .order_by(VetSchedule.day_of_week)
    )
    records = result.scalars().all()

    # 신규 계정: 주간 템플릿 없으면 기본값 7행 자동 생성
    if not records:
        for d in _DEFAULT_WEEK:
            db.add(VetSchedule(
                doctorid=current_doctor.doctorid,
                day_of_week=d["day_of_week"],
                is_open=d["is_open"],
                start_time=_parse_time(d["start_time"]) if d["start_time"] else None,
                end_time=_parse_time(d["end_time"]) if d["end_time"] else None,
                lunch_start=_parse_time(d["lunch_start"]) if d["lunch_start"] else None,
                lunch_end=_parse_time(d["lunch_end"]) if d["lunch_end"] else None,
            ))
        await db.commit()
        return WeeklyScheduleResponse(schedule=[DaySchedule(**d) for d in _DEFAULT_WEEK])

    by_dow = {r.day_of_week: r for r in records}

    schedule = []
    for d in _DEFAULT_WEEK:
        dow = d["day_of_week"]
        if dow in by_dow:
            r = by_dow[dow]
            schedule.append(DaySchedule(
                day_of_week=dow,
                is_open=r.is_open,
                start_time=_fmt(r.start_time),
                end_time=_fmt(r.end_time),
                lunch_start=_fmt(r.lunch_start),
                lunch_end=_fmt(r.lunch_end),
            ))
        else:
            schedule.append(DaySchedule(**d))

    return WeeklyScheduleResponse(schedule=schedule)


@router.put("/weekly-schedule", response_model=WeeklyScheduleResponse)
async def update_weekly_schedule(
    body: WeeklyScheduleResponse,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    for day in body.schedule:
        result = await db.execute(
            select(VetSchedule).where(
                VetSchedule.doctorid == current_doctor.doctorid,
                VetSchedule.day_of_week == day.day_of_week,
            )
        )
        record = result.scalar_one_or_none()
        st = _parse_time(day.start_time) if day.start_time else None
        et = _parse_time(day.end_time) if day.end_time else None
        ls = _parse_time(day.lunch_start) if day.lunch_start else None
        le = _parse_time(day.lunch_end) if day.lunch_end else None

        if record:
            record.is_open = day.is_open
            record.start_time = st
            record.end_time = et
            record.lunch_start = ls
            record.lunch_end = le
        else:
            db.add(VetSchedule(
                doctorid=current_doctor.doctorid,
                day_of_week=day.day_of_week,
                is_open=day.is_open,
                start_time=st,
                end_time=et,
                lunch_start=ls,
                lunch_end=le,
            ))

    await db.commit()
    return await get_weekly_schedule(db=db, current_doctor=current_doctor)


# ── 특정일 휴진 ──────────────────────────────────────────────────────────

@router.get("/closed-dates", response_model=ClosedDatesResponse)
async def get_closed_dates(
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.date.isnot(None),
            VetSchedule.is_open == False,
        ).order_by(VetSchedule.date)
    )
    records = result.scalars().all()
    return ClosedDatesResponse(dates=[r.date.isoformat() for r in records])


@router.post("/closed-dates", response_model=AddClosedDateResponse)
async def add_closed_date(
    body: AddClosedDateRequest,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    try:
        target_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    count_result = await db.execute(
        select(func.count(Schedule.scheduleid)).where(
            Schedule.doctorid == current_doctor.doctorid,
            Schedule.status == "CONFIRMED",
            Schedule.deleted_at.is_(None),
            func.date(Schedule.confirmed_time) == target_date,
        )
    )
    reservation_count = count_result.scalar() or 0

    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.date == target_date,
            VetSchedule.day_of_week.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record:
        record.is_open = False
        record.start_time = None
        record.end_time = None
    else:
        db.add(VetSchedule(
            doctorid=current_doctor.doctorid,
            date=target_date,
            is_open=False,
        ))
    await db.commit()

    return AddClosedDateResponse(
        success=True,
        has_existing_reservations=reservation_count > 0,
        reservation_count=reservation_count,
    )


@router.delete("/closed-dates/{closed_date}")
async def remove_closed_date(
    closed_date: str,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    try:
        target_date = date.fromisoformat(closed_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.date == target_date,
            VetSchedule.is_open == False,
            VetSchedule.day_of_week.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()
    return {"success": True}
