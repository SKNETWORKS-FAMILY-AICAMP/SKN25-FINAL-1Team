import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
# 충돌 검사는 schedule.py의 단일 구현(has_time_overlap)을 공유한다 — 로직 중복/드리프트 방지.
from app.crud.schedule import has_time_overlap


class TimeSlotConflict(Exception):
    """같은 날짜·시간에 이미 예약이 존재할 때"""
    pass




# 수의사 대시보드 수동 예약 기본 카테고리: 정기검진(code=1)
DEFAULT_CATEGORY_CODE = 1
DEFAULT_DURATION_MIN = 30
# 진료완료 후 남는 시간을 자동 해제하기까지의 유예(초). 오클릭/완료 되돌림 대비 버퍼.
COMPLETION_GRACE_SECONDS = 300


async def _resolve_doctor(
    db: AsyncSession,
    doctorid: int | None,
    doctor_name: str | None = None,
) -> Doctor | None:
    """doctorid를 우선 사용하고, 없으면 이름으로 검색한다. 둘 다 없으면 None 반환."""
    if doctorid is not None:
        result = await db.execute(select(Doctor).where(Doctor.doctorid == doctorid))
        return result.scalars().first()
    if doctor_name:
        result = await db.execute(select(Doctor).where(Doctor.doctor_name == doctor_name))
        return result.scalars().first()
    return None


async def get_reservations(
    db: AsyncSession,
    hospital_id: int | None = None,
    doctorid: int | None = None,
):
    """예약 목록 조회용 조인 쿼리. 소프트 삭제된 예약/진료기록은 제외한다."""
    query = (
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
    )
    if hospital_id is not None:
        query = query.where(Doctor.hospitalid == hospital_id)
    if doctorid is not None:
        query = query.where(Schedule.doctorid == doctorid)
    query = query.order_by(Schedule.confirmed_time)
    result = await db.execute(query)
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
    doctorid: int | None = None,
    doctor_name: str | None = None,
    memo: str | None = None,
    category_code: int = DEFAULT_CATEGORY_CODE,
):
    doctor = await _resolve_doctor(db, doctorid, doctor_name)
    if not doctor:
        return None

    result = await db.execute(
        select(CategoryMaster).where(CategoryMaster.code == category_code)
    )
    category = result.scalars().first()
    if not category:
        return None

    confirmed = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    new_end = confirmed + timedelta(minutes=DEFAULT_DURATION_MIN)
    if await has_time_overlap(db, doctor.doctorid, confirmed, new_end):
        raise TimeSlotConflict()

    guardian = Guardian(
        petid=pet_id,
        category_id=category.id,
        # 수의사 수동 예약은 챗봇 문진이 없어 응급도 미지정(None).
        # 목록 화면(_triage_key)에서 triage_result/triage 둘 다 없으면 '일반(normal)'으로 표시된다.
        triage_id=None,
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
    # 동시성 race로 사전 검사를 통과한 겹침은 DB no_overlap_schedule 제약이 막는다 → 충돌로 변환
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise TimeSlotConflict()
    await db.refresh(schedule)

    return schedule


async def update_reservation(
    db: AsyncSession,
    schedule_id: int,
    date_str: str | None = None,
    time_str: str | None = None,
    doctorid: int | None = None,
    doctor_name: str | None = None,
    memo: str | None = None,
):
    schedule = await get_schedule(db, schedule_id)
    if not schedule:
        return None

    guardian = await get_guardian_by_emrid(db, schedule.emrid)

    # 의사 변경이 있으면 새 의사 기준으로 충돌을 검사해야 하므로 시간 검사 전에 먼저 결정한다.
    new_doctor = await _resolve_doctor(db, doctorid, doctor_name) if (doctorid is not None or doctor_name) else None
    target_doctorid = new_doctor.doctorid if new_doctor else schedule.doctorid

    if date_str and time_str:
        confirmed = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        duration = schedule.duration_min or DEFAULT_DURATION_MIN
        new_end = confirmed + timedelta(minutes=duration)
        if await has_time_overlap(db, target_doctorid, confirmed, new_end, exclude_schedule_id=schedule_id):
            raise TimeSlotConflict()
        schedule.confirmed_time = confirmed
        schedule.confirmed_end_time = new_end
        if guardian:
            guardian.date = confirmed.date()

    if new_doctor:
        schedule.doctorid = new_doctor.doctorid

    if memo is not None and guardian:
        guardian.memo = memo

    # 동시성 race 대비: DB no_overlap_schedule 제약 위반을 충돌로 변환
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise TimeSlotConflict()
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


def schedule_slot_release(schedule_id: int, grace_seconds: int = COMPLETION_GRACE_SECONDS) -> None:
    """진료완료 직후 호출 — grace_seconds 뒤에 '실제 완료시각' 기준으로 confirmed_end_time을
    단축해 남는 시간을 다시 예약 가능하게 만든다(예상보다 일찍 끝낸 경우만).

    유예를 두는 이유: 의사가 진료완료를 오클릭하거나 곧바로 되돌릴 수 있어서,
    그 안에 상태가 바뀌면 슬롯을 풀지 않는다. 서버 재시작 시 대기 중인 건은 유실되지만
    그 경우 슬롯이 그대로 점유되는 '안전한 실패'라 데이터 정합성 문제는 없다.
    """
    from ai.tasks import safe_create_task

    completion_time = datetime.now(timezone.utc)  # 완료 누른 시각 ≈ 지금
    safe_create_task(
        _release_slot_after_grace(schedule_id, grace_seconds, completion_time),
        name=f"slot_release:{schedule_id}",
    )


async def _release_slot_after_grace(
    schedule_id: int, grace_seconds: int, completion_time: datetime
) -> None:
    """grace_seconds 대기 후, 여전히 완료 상태면 종료시각을 완료시각으로 단축한다."""
    from app.db.session import AsyncSessionLocal

    await asyncio.sleep(grace_seconds)

    async with AsyncSessionLocal() as db:
        schedule = await get_schedule(db, schedule_id)  # deleted_at IS NULL 만 조회
        if not schedule:
            return
        # 유예 동안 완료가 취소/되돌려졌으면 슬롯을 풀지 않는다(오클릭 안전장치).
        if schedule.status not in ("진료완료", "COMPLETED"):
            return
        if not schedule.confirmed_time or not schedule.confirmed_end_time:
            return

        ct = to_kst(schedule.confirmed_time)
        old_end = to_kst(schedule.confirmed_end_time)
        new_end = to_kst(completion_time)
        # 일찍 끝낸 경우에만 단축한다(시작 이후 ~ 기존 종료 이전). 종료시각을 늘리지는 않는다.
        if not (ct < new_end < old_end):
            return

        schedule.confirmed_end_time = completion_time
        schedule.duration_min = max(1, int((new_end - ct).total_seconds() // 60))
        await db.commit()
        logger.info(
            f"[slot_release] schedule_id={schedule_id} 종료시각 단축 "
            f"{old_end.strftime('%H:%M')}→{new_end.strftime('%H:%M')} — 남는 시간 예약 가능"
        )
