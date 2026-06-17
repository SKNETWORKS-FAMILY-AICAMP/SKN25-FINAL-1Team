from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_hospital
from app.crud import vet_hospital as vh_crud
from app.db.session import get_db
from app.utils.s3 import create_presigned_put

router = APIRouter(prefix="/doctor/hospital", tags=["vet-hospital"])

ALLOWED_UPLOAD_PREFIXES = {"hospital", "doctor"}


# ── 스키마 ────────────────────────────────────────────────────────────

class HospitalProfileUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    tagline: Optional[str] = None
    intro: Optional[str] = None
    bannerImage: Optional[str] = None
    bannerImagePosition: Optional[str] = None
    features: Optional[List[str]] = None


class DoctorProfileUpdate(BaseModel):
    name: Optional[str] = None
    licenseNumber: Optional[str] = None
    specialty: Optional[str] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    specialtyAreas: Optional[List[str]] = None
    profileImage: Optional[str] = None
    profileImagePosition: Optional[str] = None


class DoctorCreate(BaseModel):
    name: str


# ── 엔드포인트 ─────────────────────────────────────────────────────────

@router.get("/profile")
async def get_hospital_profile(
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    data = await vh_crud.get_vet_hospital_profile(db, current_hospital.hospitalid)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원 정보를 찾을 수 없습니다.")
    return {"code": 200, "result": data}


@router.put("/profile")
async def update_hospital_profile(
    body: HospitalProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    ok = await vh_crud.update_vet_hospital_profile(
        db, current_hospital.hospitalid, body.model_dump(exclude_unset=True)
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원 정보를 찾을 수 없습니다.")
    return {"code": 200, "result": {"success": True}}


@router.get("/doctors")
async def get_doctors(
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    doctors = await vh_crud.get_vet_doctors(db, current_hospital.hospitalid)
    return {"code": 200, "result": doctors}


@router.delete("/doctors/{did}", status_code=status.HTTP_200_OK)
async def delete_doctor(
    did: int,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    ok = await vh_crud.deactivate_vet_doctor(db, current_hospital.hospitalid, did)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="해당 의사를 삭제할 권한이 없습니다.",
        )
    return {"code": 200, "result": {"success": True}}


@router.post("/doctors", status_code=status.HTTP_201_CREATED)
async def create_doctor(
    body: DoctorCreate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    doc = await vh_crud.create_vet_doctor(db, current_hospital.hospitalid, body.name)
    return {"code": 201, "result": doc}


@router.put("/doctors/{did}/profile")
async def update_doctor_profile(
    did: int,
    body: DoctorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    ok = await vh_crud.update_vet_doctor_profile(
        db, current_hospital.hospitalid, did, body.model_dump(exclude_unset=True)
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="해당 의사 정보를 수정할 권한이 없습니다.",
        )
    return {"code": 200, "result": {"success": True}}


@router.get("/uploads/presigned-url")
async def presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    prefix: str = Query("hospital"),
    current_hospital=Depends(get_current_hospital),
):
    if prefix not in ALLOWED_UPLOAD_PREFIXES:
        prefix = "hospital"
    return {"code": 200, "result": create_presigned_put(file_name, content_type, prefix=prefix)}
