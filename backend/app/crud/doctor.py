from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.doctor import Doctor


async def get_doctors_by_hospital(db: AsyncSession, hospitalid: int) -> list[Doctor]:
    result = await db.execute(
        select(Doctor).where(Doctor.hospitalid == hospitalid, Doctor.is_active == True).order_by(Doctor.doctorid)
    )
    return list(result.scalars().all())


async def get_doctor_by_id(db: AsyncSession, doctorid: int):
    return await db.get(Doctor, doctorid)


async def get_doctor_by_license(db: AsyncSession, hospitalid: int, license_number: str):
    """계정 문의/비밀번호 재설정 시 병원 내 면허번호로 의사 조회"""
    result = await db.execute(
        select(Doctor).where(
            Doctor.hospitalid == hospitalid,
            Doctor.license_number == license_number,
        )
    )
    return result.scalar_one_or_none()


async def get_first_doctor(db: AsyncSession, hospitalid: int):
    """병원의 첫 번째 의사 반환 (기본값 fallback용)"""
    result = await db.execute(
        select(Doctor).where(Doctor.hospitalid == hospitalid).order_by(Doctor.doctorid).limit(1)
    )
    return result.scalar_one_or_none()


async def get_doctor_ids_by_hospital(db: AsyncSession, hospitalid: int) -> list[int]:
    """병원 소속 전체 doctorid 목록 반환 (비활성 포함 — 환자·알람 조회 보안 범위용)"""
    result = await db.execute(
        select(Doctor.doctorid).where(Doctor.hospitalid == hospitalid)
    )
    return list(result.scalars().all())
