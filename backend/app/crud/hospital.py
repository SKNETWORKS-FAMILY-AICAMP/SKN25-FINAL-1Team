from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.hospital import Hospital
from app.core.security import hash_password


async def get_hospital_by_loginid(db: AsyncSession, loginid: str):
    result = await db.execute(select(Hospital).where(Hospital.loginid == loginid))
    return result.scalar_one_or_none()


async def get_hospital_by_id(db: AsyncSession, hospitalid: int):
    return await db.get(Hospital, hospitalid)


async def get_hospital_by_credentials(db: AsyncSession, hospital_name: str, business_number: str):
    result = await db.execute(
        select(Hospital).where(
            Hospital.hospital_name == hospital_name,
            Hospital.business_number == business_number,
        )
    )
    return result.scalar_one_or_none()


async def update_hospital_password(db: AsyncSession, hospital: Hospital, new_password: str):
    hospital.password = hash_password(new_password)
    hospital.is_initial_password = False
    await db.commit()
    await db.refresh(hospital)
    return hospital
