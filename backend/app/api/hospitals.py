from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.crud.hospital import get_hospital_detail, search_hospitals
from app.crud import guardian_hospital as gh_crud
from app.schemas.hospital import AddHospitalRequest

router = APIRouter(tags=["hospitals"])


# ── 병원 조회 (보호자) ──────────────────────────────────────
@router.get("/hospitals")
async def list_hospitals(
    query: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"code": 200, "result": await search_hospitals(db, query)}


@router.get("/hospitals/{hospitalid}")
async def hospital_detail(
    hospitalid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    detail = await get_hospital_detail(db, hospitalid)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원을 찾을 수 없습니다.")
    return {"code": 200, "result": detail}


# ── 내 병원 (M:N) ──────────────────────────────────────────
@router.get("/guardians/me/hospitals")
async def my_hospitals(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"code": 200, "result": await gh_crud.list_my_hospitals(db, current_user.userid)}


@router.post("/guardians/me/hospitals")
async def add_my_hospital(
    body: AddHospitalRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await gh_crud.add_my_hospital(db, current_user.userid, body.hospitalid)
    return {"code": 200, "message": "등록되었습니다."}


@router.delete("/guardians/me/hospitals/{hospitalid}")
async def remove_my_hospital(
    hospitalid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await gh_crud.remove_my_hospital(db, current_user.userid, hospitalid)
    return {"code": 200, "message": "해제되었습니다."}


@router.put("/guardians/me/hospitals/{hospitalid}/primary")
async def set_primary_hospital(
    hospitalid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await gh_crud.set_primary(db, current_user.userid, hospitalid)
    return {"code": 200, "message": "기본 병원으로 설정되었습니다."}
