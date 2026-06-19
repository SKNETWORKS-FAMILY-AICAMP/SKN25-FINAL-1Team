"""병원 간 데이터 격리(tenant isolation) 가드.

수의사(병원) 인증만으로는 부족하다 — 인증된 병원이 *자기 병원 소속* 레코드에만
접근하도록, 대상 레코드를 그 병원의 doctor(→hospitalid)까지 join 해 소속을 검증한다.

엔드포인트에서 schedule_id / doctor_emrid / prescription_id / 가디언 emrid 를
받을 때, CRUD 호출 전에 아래 가드로 소속을 확인하고 불일치 시 404 를 반환한다.
(존재 여부를 숨기기 위해 403 대신 404 를 쓴다 — 다른 병원 ID 열거를 막음)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor
from app.models.emr import EMR
from app.models.prescription import Prescription
from app.models.schedule import Schedule


async def schedule_in_hospital(db: AsyncSession, schedule_id: int, hospitalid: int) -> bool:
    """schedule_id 가 해당 병원 소속 원장의 예약인지."""
    row = await db.execute(
        select(Schedule.scheduleid)
        .join(Doctor, Schedule.doctorid == Doctor.doctorid)
        .where(Schedule.scheduleid == schedule_id, Doctor.hospitalid == hospitalid)
    )
    return row.first() is not None


async def guardian_emrid_in_hospital(db: AsyncSession, emrid: int, hospitalid: int) -> bool:
    """가디언(문진) emrid 에 연결된 예약이 해당 병원 소속인지.

    (doctor EMR 의 PK 가 아니라 scheduleDB.emrid = guardianDB.emrid 기준)
    """
    row = await db.execute(
        select(Schedule.scheduleid)
        .join(Doctor, Schedule.doctorid == Doctor.doctorid)
        .where(Schedule.emrid == emrid, Doctor.hospitalid == hospitalid)
    )
    return row.first() is not None


async def emr_in_hospital(db: AsyncSession, doctor_emrid: int, hospitalid: int) -> bool:
    """doctor_emrid(진료 EMR PK)가 해당 병원 소속 원장의 EMR 인지."""
    row = await db.execute(
        select(EMR.doctor_emrid)
        .join(Doctor, EMR.doctorid == Doctor.doctorid)
        .where(EMR.doctor_emrid == doctor_emrid, Doctor.hospitalid == hospitalid)
    )
    return row.first() is not None


async def prescription_in_hospital(db: AsyncSession, prescription_id: int, hospitalid: int) -> bool:
    """prescription_id 가 해당 병원 소속 원장의 EMR 에 속한 처방인지."""
    row = await db.execute(
        select(Prescription.prescriptionid)
        .join(EMR, Prescription.doctor_emrid == EMR.doctor_emrid)
        .join(Doctor, EMR.doctorid == Doctor.doctorid)
        .where(Prescription.prescriptionid == prescription_id, Doctor.hospitalid == hospitalid)
    )
    return row.first() is not None
