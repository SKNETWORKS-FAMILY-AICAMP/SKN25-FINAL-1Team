from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import Schedule
from app.models.guardian import Guardian
from app.models.pet import Pet
from app.models.triage_result import TriageResult
from app.models.doctor import Doctor
from app.utils.timezone import KST


async def get_doctor_day_schedules(
    db: AsyncSession,
    doctor_id: int,
    start: datetime,
    end: datetime,
):
    """특정 수의사의 하루치 예약을 조인 조회한다."""
    kst_start = start.replace(tzinfo=KST)
    kst_end = end.replace(tzinfo=KST)

    result = await db.execute(
        select(Schedule, Guardian, Pet, TriageResult)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .outerjoin(TriageResult, Guardian.emrid == TriageResult.emrid)
        .where(Schedule.doctorid == doctor_id)
        .where(Schedule.confirmed_time >= kst_start)
        .where(Schedule.confirmed_time < kst_end)
        .where(Schedule.deleted_at.is_(None))
        .where(Schedule.status != "CANCELLED")
        .where(Guardian.deleted_at.is_(None))
        .order_by(Schedule.confirmed_time.asc())
    )
    return result.all()


async def get_hospital_day_schedules(
    db: AsyncSession,
    doctor_ids: list[int],
    start: datetime,
    end: datetime,
):
    """병원 소속 전체 수의사의 하루치 예약을 통합 조회한다."""
    kst_start = start.replace(tzinfo=KST)
    kst_end = end.replace(tzinfo=KST)

    result = await db.execute(
        select(Schedule, Guardian, Pet, TriageResult, Doctor)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .outerjoin(TriageResult, Guardian.emrid == TriageResult.emrid)
        .join(Doctor, Schedule.doctorid == Doctor.doctorid)
        .where(Schedule.doctorid.in_(doctor_ids))
        .where(Schedule.confirmed_time >= kst_start)
        .where(Schedule.confirmed_time < kst_end)
        .where(Schedule.deleted_at.is_(None))
        .where(Schedule.status != "CANCELLED")
        .where(Guardian.deleted_at.is_(None))
        .order_by(Schedule.confirmed_time.asc())
    )
    return result.all()
