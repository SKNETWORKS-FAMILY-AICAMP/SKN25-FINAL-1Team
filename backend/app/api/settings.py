from datetime import date, time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.vet_schedule import VetSchedule

router = APIRouter(prefix="/doctor/settings", tags=["doctor-settings"])


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


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


@router.get("/operating-hours", response_model=OperatingHoursResponse)
async def get_operating_hours(
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    result = await db.execute(
        select(VetSchedule)
        .where(VetSchedule.doctorid == current_doctor.doctorid)
        .order_by(VetSchedule.date.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return OperatingHoursResponse(
            start_time="09:00",
            end_time="18:00",
            lunch_start="12:00",
            lunch_end="13:00",
        )
    return OperatingHoursResponse(
        start_time=record.start_time.strftime("%H:%M"),
        end_time=record.end_time.strftime("%H:%M"),
        lunch_start=record.lunch_start.strftime("%H:%M") if record.lunch_start else "12:00",
        lunch_end=record.lunch_end.strftime("%H:%M") if record.lunch_end else "13:00",
    )


@router.put("/operating-hours", response_model=OperatingHoursResponse)
async def update_operating_hours(
    body: OperatingHoursRequest,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    today = date.today()
    result = await db.execute(
        select(VetSchedule).where(
            VetSchedule.doctorid == current_doctor.doctorid,
            VetSchedule.date == today,
        )
    )
    record = result.scalar_one_or_none()

    if record:
        record.start_time = _parse_time(body.start_time)
        record.end_time = _parse_time(body.end_time)
        record.lunch_start = _parse_time(body.lunch_start)
        record.lunch_end = _parse_time(body.lunch_end)
    else:
        db.add(
            VetSchedule(
                doctorid=current_doctor.doctorid,
                date=today,
                start_time=_parse_time(body.start_time),
                end_time=_parse_time(body.end_time),
                lunch_start=_parse_time(body.lunch_start),
                lunch_end=_parse_time(body.lunch_end),
            )
        )
    await db.commit()
    return OperatingHoursResponse(**body.model_dump())
