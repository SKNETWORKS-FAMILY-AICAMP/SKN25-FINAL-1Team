import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.timezone import KST

logger = logging.getLogger(__name__)

from app.models.schedule import Schedule
from app.models.guardian import Guardian
from app.models.pet import Pet
from app.models.user import User
from app.models.doctor import Doctor
from app.models.emr import EMR
from app.models.master import TriageMaster, CategoryMaster
from app.models.triage_result import TriageResult
from app.utils.timezone import to_kst


class TimeSlotConflict(Exception):
    """같은 날짜·시간에 이미 예약이 존재할 때"""
    pass




# 수의사 대시보드 수동 예약 기본 카테고리: 정기검진(code=1)
DEFAULT_CATEGORY_CODE = 1
# 예약 추가 시 기본 응급도(일반, code=3)
DEFAULT_TRIAGE_CODE = 3
DEFAULT_DURATION_MIN = 30


async def _resolve_doctor(db: AsyncSession, doctor_name: str | None) -> Doctor | None:
    doctor = None
    if doctor_name:
        result = await db.execute(
            select(Doctor).where(Doctor.doctor_name == doctor_name)
        )
        doctor = result.scalars().first()
    if not doctor:
        result = await db.execute(select(Doctor))
        doctor = result.scalars().first()
    return doctor


async def has_time_conflict(
    db: AsyncSession,
    confirmed: datetime,
    duration_min: int = DEFAULT_DURATION_MIN,
    exclude_schedule_id: int | None = None,
) -> bool:
    """새 예약(confirmed ~ confirmed+duration_min)이 기존 예약과 겹치는지 확인."""
    target_date = confirmed.date()
    new_end = confirmed + timedelta(minutes=duration_min)

    stmt = (
        select(Schedule)
        .where(Schedule.confirmed_time.isnot(None))
        .where(Schedule.deleted_at.is_(None))
        .where(Schedule.status != "CANCELLED")
    )
    if exclude_schedule_id is not None:
        stmt = stmt.where(Schedule.scheduleid != exclude_schedule_id)

    result = await db.execute(stmt)
    for s in result.scalars().all():
        ct = to_kst(s.confirmed_time)
        if not ct or ct.date() != target_date:
            continue
        et = to_kst(s.confirmed_end_time) if s.confirmed_end_time else ct + timedelta(minutes=s.duration_min)
        if confirmed < et and new_end > ct:
            return True

    return False


async def get_reservations(db: AsyncSession):
    """예약 목록 조회용 조인 쿼리. 소프트 삭제된 예약/진료기록은 제외한다."""
    result = await db.execute(
        select(
            Schedule,
            Guardian,
            Pet,
            User,
            Doctor,
            TriageMaster,
            CategoryMaster,
            TriageResult,
        )
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .join(User, Pet.userid == User.userid)
        .join(Doctor, Schedule.doctorid == Doctor.doctorid)
        .outerjoin(TriageMaster, Guardian.triage_id == TriageMaster.id)
        .outerjoin(CategoryMaster, Guardian.category_id == CategoryMaster.id)
        .outerjoin(TriageResult, Guardian.emrid == TriageResult.emrid)
        .where(Schedule.deleted_at.is_(None))
        .where(Guardian.deleted_at.is_(None))
        .where(Schedule.status != "CANCELLED")
        .order_by(Schedule.confirmed_time)
    )
    return result.all()


async def get_schedule(db: AsyncSession, schedule_id: int) -> Schedule | None:
    """소프트 삭제되지 않은 예약 단건 조회."""
    result = await db.execute(
        select(Schedule).where(
            Schedule.scheduleid == schedule_id,
            Schedule.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_guardian_by_emrid(db: AsyncSession, emrid: int) -> Guardian | None:
    result = await db.execute(
        select(Guardian).where(
            Guardian.emrid == emrid,
            Guardian.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_default_category(db: AsyncSession) -> CategoryMaster | None:
    result = await db.execute(
        select(CategoryMaster).where(CategoryMaster.code == DEFAULT_CATEGORY_CODE)
    )
    category = result.scalars().first()
    if category:
        return category
    result = await db.execute(select(CategoryMaster))
    return result.scalars().first()


async def get_default_triage(db: AsyncSession) -> TriageMaster | None:
    result = await db.execute(
        select(TriageMaster).where(TriageMaster.code == DEFAULT_TRIAGE_CODE)
    )
    return result.scalars().first()


async def update_reservation_status(
    db: AsyncSession,
    schedule_id: int,
    status: str,
    vet_memo: str | None = None,
    attachments: list[dict] | None = None,
    prescriptions: list[dict] | None = None,
):
    from app.models.drug import Drug
    from app.models.prescription import Prescription

    schedule = await get_schedule(db, schedule_id)
    if not schedule:
        return None

    schedule.status = status

    if status in ("진료완료", "COMPLETED"):
        guardian = await get_guardian_by_emrid(db, schedule.emrid)
        if guardian:
            result = await db.execute(
                select(EMR).where(EMR.scheduleid == schedule.scheduleid)
            )
            emr = result.scalar_one_or_none()
            if not emr:
                emr = EMR(
                    petid=guardian.petid,
                    doctorid=schedule.doctorid,
                    scheduleid=schedule.scheduleid,
                )
                db.add(emr)

            emr.vet_memo = vet_memo
            emr.attachments = attachments or []

            if prescriptions:
                await db.flush()  # doctor_emrid 확정
                for presc in prescriptions:
                    drug_row = await db.execute(
                        select(Drug).where(Drug.name == presc.get("drug_name"))
                    )
                    drug = drug_row.scalar_one_or_none()
                    if drug:
                        db.add(Prescription(
                            doctor_emrid=emr.doctor_emrid,
                            drug_id=drug.drugid,
                            form=presc.get("form"),
                            dosage=presc.get("dosage"),
                            duration_days=presc.get("duration_days"),
                        ))

    await db.commit()
    await db.refresh(schedule)
    return schedule


async def create_reservation(
    db: AsyncSession,
    pet_id: int,
    date_str: str,
    time_str: str,
    doctor_name: str | None = None,
    memo: str | None = None,
):
    doctor = await _resolve_doctor(db, doctor_name)
    if not doctor:
        return None

    category = await get_default_category(db)
    if not category:
        return None

    triage = await get_default_triage(db)

    confirmed = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    if await has_time_conflict(db, confirmed, duration_min=DEFAULT_DURATION_MIN):
        raise TimeSlotConflict()

    guardian = Guardian(
        petid=pet_id,
        category_id=category.id,
        triage_id=triage.id if triage else None,
        date=datetime.strptime(date_str, "%Y-%m-%d").date(),
        memo=memo,
    )
    db.add(guardian)
    await db.flush()

    schedule = Schedule(
        emrid=guardian.emrid,
        doctorid=doctor.doctorid,
        duration_min=DEFAULT_DURATION_MIN,
        confirmed_time=confirmed,
        confirmed_end_time=confirmed + timedelta(minutes=DEFAULT_DURATION_MIN),
        status="CONFIRMED",
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return schedule


async def update_reservation(
    db: AsyncSession,
    schedule_id: int,
    date_str: str | None = None,
    time_str: str | None = None,
    doctor_name: str | None = None,
    memo: str | None = None,
):
    schedule = await get_schedule(db, schedule_id)
    if not schedule:
        return None

    guardian = await get_guardian_by_emrid(db, schedule.emrid)

    if date_str and time_str:
        confirmed = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        duration = schedule.duration_min or DEFAULT_DURATION_MIN
        if await has_time_conflict(db, confirmed, duration_min=duration, exclude_schedule_id=schedule_id):
            raise TimeSlotConflict()
        schedule.confirmed_time = confirmed
        schedule.confirmed_end_time = confirmed + timedelta(minutes=duration)
        if guardian:
            guardian.date = confirmed.date()

    if doctor_name:
        doctor = await _resolve_doctor(db, doctor_name)
        if doctor:
            schedule.doctorid = doctor.doctorid

    if memo is not None and guardian:
        guardian.memo = memo

    await db.commit()
    await db.refresh(schedule)

    return schedule


async def delete_reservation(db: AsyncSession, schedule_id: int) -> bool:
    """하드 삭제 대신 deleted_at 타임스탬프를 기록하는 소프트 삭제."""
    schedule = await get_schedule(db, schedule_id)
    if not schedule:
        return False

    guardian = await get_guardian_by_emrid(db, schedule.emrid)
    logger.info(
        f"[delete_reservation] schedule_id={schedule_id} "
        f"emrid={schedule.emrid} status={schedule.status}"
    )

    now = datetime.now(timezone.utc)
    schedule.deleted_at = now
    schedule.status = "CANCELLED"
    if guardian:
        guardian.deleted_at = now

    await db.commit()
    logger.info(f"[delete_reservation] done schedule_id={schedule_id}")
    return True
