from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guardian_hospital import GuardianHospital
from app.models.hospital import Hospital


async def list_my_hospitals(db: AsyncSession, userid: int) -> list[dict]:
    result = await db.execute(
        select(GuardianHospital, Hospital)
        .join(Hospital, Hospital.hospitalid == GuardianHospital.hospitalid)
        .where(GuardianHospital.userid == userid)
        .order_by(GuardianHospital.is_primary.desc(), GuardianHospital.created_at)
    )
    return [
        {
            "hospitalid": h.hospitalid,
            "name": h.hospital_name,
            "is_primary": gh.is_primary,
            "is_active": h.is_active,  # 폐업 병원은 보호자 목록에서 뱃지 표시용
        }
        for gh, h in result.all()
    ]


async def add_my_hospital(db: AsyncSession, userid: int, hospitalid: int) -> None:
    exists = await db.execute(
        select(GuardianHospital).where(
            GuardianHospital.userid == userid,
            GuardianHospital.hospitalid == hospitalid,
        )
    )
    if exists.scalar_one_or_none():
        return

    # 첫 등록이면 자동으로 기본 병원
    any_existing = await db.execute(
        select(GuardianHospital).where(GuardianHospital.userid == userid)
    )
    is_first = any_existing.scalars().first() is None

    db.add(GuardianHospital(userid=userid, hospitalid=hospitalid, is_primary=is_first))
    await db.commit()


async def remove_my_hospital(db: AsyncSession, userid: int, hospitalid: int) -> None:
    await db.execute(
        delete(GuardianHospital).where(
            GuardianHospital.userid == userid,
            GuardianHospital.hospitalid == hospitalid,
        )
    )
    await db.commit()


async def set_primary(db: AsyncSession, userid: int, hospitalid: int) -> None:
    await db.execute(
        update(GuardianHospital)
        .where(GuardianHospital.userid == userid)
        .values(is_primary=False)
    )
    await db.execute(
        update(GuardianHospital)
        .where(
            GuardianHospital.userid == userid,
            GuardianHospital.hospitalid == hospitalid,
        )
        .values(is_primary=True)
    )
    await db.commit()
