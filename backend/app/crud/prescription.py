from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drug import Drug
from app.models.prescription import Prescription


async def search_drugs(db: AsyncSession, keyword: str, limit: int = 10):
    result = await db.execute(
        select(Drug)
        .where(Drug.name.ilike(f"%{keyword}%"))
        .limit(limit)
    )
    return result.scalars().all()


async def create_prescription(db: AsyncSession, doctor_emrid: int, drug_id: int, form: str = None, dosage: str = None, duration_days: int = None):
    prescription = Prescription(
        doctor_emrid=doctor_emrid,
        drug_id=drug_id,
        form=form,
        dosage=dosage,
        duration_days=duration_days,
    )
    db.add(prescription)
    await db.commit()
    await db.refresh(prescription)
    return prescription


async def get_prescriptions_by_emrid(db: AsyncSession, doctor_emrid: int):
    result = await db.execute(
        select(Prescription, Drug)
        .join(Drug, Prescription.drug_id == Drug.drugid)
        .where(Prescription.doctor_emrid == doctor_emrid)
    )
    return result.all()


async def delete_prescription(db: AsyncSession, prescription_id: int):
    result = await db.execute(
        select(Prescription).where(Prescription.prescriptionid == prescription_id)
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        return False
    await db.delete(prescription)
    await db.commit()
    return True
