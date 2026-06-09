from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.crud.prescription import (
    search_drugs,
    create_prescription,
    get_prescriptions_by_emrid,
    delete_prescription,
)
from app.schemas.prescription import (
    DrugSearchResponse,
    DrugSearchResult,
    PrescriptionCreate,
    PrescriptionListResponse,
    PrescriptionResponse,
)
from app.schemas.common import MessageResponse
from app.core.dependencies import get_current_doctor

router = APIRouter(tags=["prescriptions"])


@router.get("/drugs/search", response_model=DrugSearchResponse)
async def search_drug(
    keyword: str,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_doctor),
):
    if not keyword or len(keyword.strip()) < 1:
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")

    drugs = await search_drugs(db, keyword.strip())
    return DrugSearchResponse(
        result=[DrugSearchResult.model_validate(d) for d in drugs]
    )


@router.post("/prescriptions", response_model=PrescriptionResponse, status_code=201)
async def add_prescription(
    payload: PrescriptionCreate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_doctor),
):
    prescription = await create_prescription(
        db,
        doctor_emrid=payload.doctor_emrid,
        drug_id=payload.drug_id,
        form=payload.form,
        dosage=payload.dosage,
        duration_days=payload.duration_days,
    )
    return prescription


@router.get("/prescriptions/{doctor_emrid}", response_model=PrescriptionListResponse)
async def get_prescriptions(
    doctor_emrid: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_doctor),
):
    rows = await get_prescriptions_by_emrid(db, doctor_emrid)
    result = [
        PrescriptionResponse(
            prescriptionid=p.prescriptionid,
            doctor_emrid=p.doctor_emrid,
            drug_id=p.drug_id,
            drug_name=d.name,
            form=p.form,
            dosage=p.dosage,
            duration_days=p.duration_days,
        )
        for p, d in rows
    ]
    return PrescriptionListResponse(result=result)


@router.delete("/prescriptions/{prescription_id}", response_model=MessageResponse, status_code=200)
async def remove_prescription(
    prescription_id: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(get_current_doctor),
):
    deleted = await delete_prescription(db, prescription_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="처방전을 찾을 수 없습니다.")
    return MessageResponse(message="처방전이 삭제되었습니다.")
