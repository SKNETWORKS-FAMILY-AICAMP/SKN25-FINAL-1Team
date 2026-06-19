from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_hospital
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.schedule import Schedule
from app.models.vet_schedule import HospitalWeeklySchedule, HospitalClosedDate, VetWeeklySchedule

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


def _build_schedule_from_records(records) -> list[DaySchedule]:
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
    return schedule


# ── 병원 운영시간 (하위 호환용 단일 시간대 반환) ─────────────────────────

@router.get("/operating-hours", response_model=OperatingHoursResponse)
async def get_operating_hours(
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    result = await db.execute(
        select(HospitalWeeklySchedule)
        .where(
            HospitalWeeklySchedule.hospitalid == current_hospital.hospitalid,
            HospitalWeeklySchedule.is_open == True,
        )
        .order_by(HospitalWeeklySchedule.day_of_week)
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record and record.start_time:
        return OperatingHoursResponse(
            start_time=_fmt(record.start_time),
            end_time=_fmt(record.end_time),
            lunch_start=_fmt(record.lunch_start) or "12:00",
            lunch_end=_fmt(record.lunch_end) or "13:00",
        )
    return OperatingHoursResponse(start_time="09:00", end_time="18:00", lunch_start="12:00", lunch_end="13:00")


@router.put("/operating-hours", response_model=OperatingHoursResponse)
async def update_operating_hours(
    body: OperatingHoursRequest,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    hid = current_hospital.hospitalid
    for dow in range(5):
        result = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == hid,
                HospitalWeeklySchedule.day_of_week == dow,
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
            db.add(HospitalWeeklySchedule(
                hospitalid=hid,
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
# doctorid 없음 → 병원 운영시간 (hospital_weekly_scheduleDB)
# doctorid 있음 → 의사별 근무시간 (vet_weekly_scheduleDB)

@router.get("/weekly-schedule", response_model=WeeklyScheduleResponse)
async def get_weekly_schedule(
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    if doctorid is not None:
        return await _get_vet_weekly_schedule(db, doctorid)
    return await _get_hospital_weekly_schedule(db, current_hospital.hospitalid)


@router.put("/weekly-schedule", response_model=WeeklyScheduleResponse)
async def update_weekly_schedule(
    body: WeeklyScheduleResponse,
    doctorid: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    if doctorid is not None:
        return await _update_vet_weekly_schedule(db, doctorid, body.schedule)
    return await _update_hospital_weekly_schedule(db, current_hospital.hospitalid, body.schedule)


# ── 병원 주간 스케줄 내부 함수 ───────────────────────────────────────────

async def _get_hospital_weekly_schedule(db: AsyncSession, hospitalid: int) -> WeeklyScheduleResponse:
    result = await db.execute(
        select(HospitalWeeklySchedule)
        .where(HospitalWeeklySchedule.hospitalid == hospitalid)
        .order_by(HospitalWeeklySchedule.day_of_week)
    )
    records = result.scalars().all()

    if not records:
        for d in _DEFAULT_WEEK:
            db.add(HospitalWeeklySchedule(
                hospitalid=hospitalid,
                day_of_week=d["day_of_week"],
                is_open=d["is_open"],
                start_time=_parse_time(d["start_time"]) if d["start_time"] else None,
                end_time=_parse_time(d["end_time"]) if d["end_time"] else None,
                lunch_start=_parse_time(d["lunch_start"]) if d["lunch_start"] else None,
                lunch_end=_parse_time(d["lunch_end"]) if d["lunch_end"] else None,
            ))
        await db.commit()
        return WeeklyScheduleResponse(schedule=[DaySchedule(**d) for d in _DEFAULT_WEEK])

    return WeeklyScheduleResponse(schedule=_build_schedule_from_records(records))


async def _update_hospital_weekly_schedule(
    db: AsyncSession, hospitalid: int, days: list[DaySchedule]
) -> WeeklyScheduleResponse:
    for day in days:
        result = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == hospitalid,
                HospitalWeeklySchedule.day_of_week == day.day_of_week,
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
            db.add(HospitalWeeklySchedule(
                hospitalid=hospitalid,
                day_of_week=day.day_of_week,
                is_open=day.is_open,
                start_time=st,
                end_time=et,
                lunch_start=ls,
                lunch_end=le,
            ))

    await db.commit()
    return await _get_hospital_weekly_schedule(db, hospitalid)


# ── 의사별 주간 스케줄 내부 함수 ─────────────────────────────────────────

async def _get_vet_weekly_schedule(db: AsyncSession, doctorid: int) -> WeeklyScheduleResponse:
    result = await db.execute(
        select(VetWeeklySchedule)
        .where(VetWeeklySchedule.doctorid == doctorid)
        .order_by(VetWeeklySchedule.day_of_week)
    )
    records = result.scalars().all()

    if not records:
        for d in _DEFAULT_WEEK:
            db.add(VetWeeklySchedule(
                doctorid=doctorid,
                day_of_week=d["day_of_week"],
                is_open=d["is_open"],
                start_time=_parse_time(d["start_time"]) if d["start_time"] else None,
                end_time=_parse_time(d["end_time"]) if d["end_time"] else None,
                lunch_start=_parse_time(d["lunch_start"]) if d["lunch_start"] else None,
                lunch_end=_parse_time(d["lunch_end"]) if d["lunch_end"] else None,
            ))
        await db.commit()
        return WeeklyScheduleResponse(schedule=[DaySchedule(**d) for d in _DEFAULT_WEEK])

    return WeeklyScheduleResponse(schedule=_build_schedule_from_records(records))


async def _update_vet_weekly_schedule(
    db: AsyncSession, doctorid: int, days: list[DaySchedule]
) -> WeeklyScheduleResponse:
    doctor = await db.get(Doctor, doctorid)
    if doctor:
        hosp_rows = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == doctor.hospitalid
            )
        )
        hosp_by_dow = {r.day_of_week: r for r in hosp_rows.scalars().all()}

        _DAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

        # 병원 운영시간이 아직 설정되지 않은 경우 검증 건너뜀
        if hosp_by_dow:
            for day in days:
                if not day.is_open:
                    continue
                dow_label = _DAY_KR[day.day_of_week]
                hosp = hosp_by_dow.get(day.day_of_week)
                if hosp is None or not hosp.is_open:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{dow_label}: 병원이 운영하지 않는 요일에 의사 근무시간을 설정할 수 없습니다.",
                    )
                if day.start_time and hosp.start_time and _parse_time(day.start_time) < hosp.start_time:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{dow_label}: 의사 근무 시작 시간({day.start_time})이 병원 운영 시작 시간({_fmt(hosp.start_time)})보다 이를 수 없습니다.",
                    )
                if day.end_time and hosp.end_time and _parse_time(day.end_time) > hosp.end_time:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{dow_label}: 의사 근무 종료 시간({day.end_time})이 병원 운영 종료 시간({_fmt(hosp.end_time)})을 초과할 수 없습니다.",
                    )

        # 변경 후 의사 전체 합이 병원 운영시간을 커버하는지 확인
        other_docs = (await db.execute(
            select(Doctor).where(
                Doctor.hospitalid == doctor.hospitalid,
                Doctor.doctorid != doctorid,
                Doctor.is_active == True,
            )
        )).scalars().all()

        other_scheds: dict[int, dict[int, VetWeeklySchedule]] = {}
        for od in other_docs:
            rows = (await db.execute(
                select(VetWeeklySchedule).where(VetWeeklySchedule.doctorid == od.doctorid)
            )).scalars().all()
            other_scheds[od.doctorid] = {r.day_of_week: r for r in rows}

        new_by_dow = {day.day_of_week: day for day in days}

        for dow, hosp in hosp_by_dow.items():
            if not hosp.is_open or not hosp.start_time or not hosp.end_time:
                continue
            all_starts, all_ends = [], []
            # 현재 의사의 새 스케줄 반영
            if dow in new_by_dow:
                nd = new_by_dow[dow]
                if nd.is_open and nd.start_time and nd.end_time:
                    all_starts.append(_parse_time(nd.start_time))
                    all_ends.append(_parse_time(nd.end_time))
            # 다른 의사들의 기존 스케줄
            for od_scheds in other_scheds.values():
                od_row = od_scheds.get(dow)
                if od_row and od_row.is_open and od_row.start_time and od_row.end_time:
                    all_starts.append(od_row.start_time)
                    all_ends.append(od_row.end_time)
            if not all_starts:
                continue
            dow_label = _DAY_KR[dow]
            if min(all_starts) > hosp.start_time:
                raise HTTPException(
                    status_code=400,
                    detail=f"{dow_label}: 변경 시 병원 운영 시작 시간({_fmt(hosp.start_time)})을 커버하는 의사가 없어집니다.",
                )
            if max(all_ends) < hosp.end_time:
                raise HTTPException(
                    status_code=400,
                    detail=f"{dow_label}: 변경 시 병원 운영 종료 시간({_fmt(hosp.end_time)})을 커버하는 의사가 없어집니다.",
                )

    for day in days:
        result = await db.execute(
            select(VetWeeklySchedule).where(
                VetWeeklySchedule.doctorid == doctorid,
                VetWeeklySchedule.day_of_week == day.day_of_week,
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
            db.add(VetWeeklySchedule(
                doctorid=doctorid,
                day_of_week=day.day_of_week,
                is_open=day.is_open,
                start_time=st,
                end_time=et,
                lunch_start=ls,
                lunch_end=le,
            ))

    await db.commit()
    return await _get_vet_weekly_schedule(db, doctorid)


# ── 특정일 휴진 ──────────────────────────────────────────────────────────

@router.get("/closed-dates", response_model=ClosedDatesResponse)
async def get_closed_dates(
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    result = await db.execute(
        select(HospitalClosedDate)
        .where(HospitalClosedDate.hospitalid == current_hospital.hospitalid)
        .order_by(HospitalClosedDate.date)
    )
    records = result.scalars().all()
    return ClosedDatesResponse(dates=[r.date.isoformat() for r in records])


@router.post("/closed-dates", response_model=AddClosedDateResponse)
async def add_closed_date(
    body: AddClosedDateRequest,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    try:
        target_date = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    hid = current_hospital.hospitalid

    count_result = await db.execute(
        select(func.count(Schedule.scheduleid))
        .join(Doctor, Schedule.doctorid == Doctor.doctorid)
        .where(
            Doctor.hospitalid == hid,
            Schedule.status == "CONFIRMED",
            Schedule.deleted_at.is_(None),
            func.date(Schedule.confirmed_time) == target_date,
        )
    )
    reservation_count = count_result.scalar() or 0

    result = await db.execute(
        select(HospitalClosedDate).where(
            HospitalClosedDate.hospitalid == hid,
            HospitalClosedDate.date == target_date,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        db.add(HospitalClosedDate(hospitalid=hid, date=target_date))
        await db.commit()

    return AddClosedDateResponse(
        success=True,
        has_existing_reservations=reservation_count > 0,
        reservation_count=reservation_count,
    )


@router.delete("/closed-dates/{closed_date}", response_model=DeleteClosedDateResponse)
async def remove_closed_date(
    closed_date: str,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    try:
        target_date = date.fromisoformat(closed_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    result = await db.execute(
        select(HospitalClosedDate).where(
            HospitalClosedDate.hospitalid == current_hospital.hospitalid,
            HospitalClosedDate.date == target_date,
        )
    )
    record = result.scalar_one_or_none()
    if record:
        await db.delete(record)
        await db.commit()
    return DeleteClosedDateResponse(success=True)
