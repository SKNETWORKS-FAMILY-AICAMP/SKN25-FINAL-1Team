from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_hospital
from app.db.session import get_db
from app.crud.doctor import get_first_doctor
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


class DeleteClosedDateResponse(BaseModel):
    success: bool


# ── 유틸 ────────────────────────────────────────────────────────────────

def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _fmt(t: Optional[time]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


async def _resolve_doctorid(db: AsyncSession, hospitalid: int, doctorid: Optional[int]) -> int:
    """doctorid 파라미터가 없으면 병원의 첫 번째 의사를 기본값으로 사용"""
    if doctorid is not None:
        return doctorid
    first = await get_first_doctor(db, hospitalid)
    if first is None:
        raise HTTPException(status_code=404, detail="등록된 수의사가 없습니다.")
    return first.doctorid


# ── 기존 운영시간 (하위 호환) ────────────────────────────────────────────

@router.get("/operating-hours", response_model=OperatingHoursResponse)
async def get_operating_hours(
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)
    result = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == did,
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
    result2 = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == did,
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
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)
    for dow in range(5):
        result = await db.execute(
            select(VetSchedule).where(
                VetSchedule.doctorid == did,
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
                doctorid=did,
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
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)
    result = await db.execute(
        select(VetSchedule)
        .where(
            VetSchedule.doctorid == did,
            VetSchedule.day_of_week.isnot(None),
        )
        .order_by(VetSchedule.day_of_week)
    )
    records = result.scalars().all()

    if not records:
        for d in _DEFAULT_WEEK:
            db.add(VetSchedule(
                doctorid=did,
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
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)
    for day in body.schedule:
        result = await db.execute(
            select(VetSchedule).where(
                VetSchedule.doctorid == did,
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
                doctorid=did,
                day_of_week=day.day_of_week,
                is_open=day.is_open,
                start_time=st,
                end_time=et,
                lunch_start=ls,
                lunch_end=le,
            ))

    await db.commit()
    return await get_weekly_schedule(doctorid=doctorid, db=db, current_hospital=current_hospital)


# ── 특정일 휴진 ──────────────────────────────────────────────────────────

@router.get("/closed-dates", response_model=ClosedDatesResponse)
async def get_closed_dates(
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)
    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == did,
            VetSchedule.date.isnot(None),
            VetSchedule.is_open == False,
        ).order_by(VetSchedule.date)
    )
    records = result.scalars().all()
    return ClosedDatesResponse(dates=[r.date.isoformat() for r in records])


@router.post("/closed-dates", response_model=AddClosedDateResponse)
async def add_closed_date(
    body: AddClosedDateRequest,
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    try:
        target_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)

    count_result = await db.execute(
        select(func.count(Schedule.scheduleid)).where(
            Schedule.doctorid == did,
            Schedule.status == "CONFIRMED",
            Schedule.deleted_at.is_(None),
            func.date(Schedule.confirmed_time) == target_date,
        )
    )
    reservation_count = count_result.scalar() or 0

    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == did,
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
            doctorid=did,
            date=target_date,
            is_open=False,
        ))
    await db.commit()

    return AddClosedDateResponse(
        success=True,
        has_existing_reservations=reservation_count > 0,
        reservation_count=reservation_count,
    )


@router.delete("/closed-dates/{closed_date}", response_model=DeleteClosedDateResponse)
async def remove_closed_date(
    closed_date: str,
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    try:
        target_date = date.fromisoformat(closed_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    did = await _resolve_doctorid(db, current_hospital.hospitalid, doctorid)

    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == did,
            VetSchedule.date == target_date,
            VetSchedule.is_open == False,
            VetSchedule.day_of_week.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()
    return DeleteClosedDateResponse(success=True)
