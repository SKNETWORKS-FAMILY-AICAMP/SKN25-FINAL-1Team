from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.pet import PetCreate, PetListResponse, PetDetailResponse, PetUpdate, PetCreateResponse
from app.schemas.common import MessageResponse
from app.crud.pet import (
    create_pet,
    get_pets_by_userid,
    get_archived_pets_by_userid,
    get_pet_by_id,
    update_pet,
    archive_pet,
    restore_pet,
    pet_has_records,
    hard_delete_pet,
)
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/pets", tags=["pets"])


@router.get("", response_model=list[PetListResponse], status_code=200)
async def get_pets(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    pets = await get_pets_by_userid(db, current_user.userid)
    return [
        PetListResponse(
            pet_id=pet.petid,
            petname=pet.petname,
            species=pet.species,
            breed=pet.breed,
            gender=pet.gender,
            profile_image=pet.profile_image,
        )
        for pet in pets
    ]


@router.post("", response_model=PetCreateResponse, status_code=201)
async def register_pet(
    pet: PetCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not pet.petname:
        raise HTTPException(status_code=400, detail="반려동물 이름을 입력해주세요.")
    if not pet.species:
        raise HTTPException(status_code=400, detail="종을 선택해주세요.")

    new_pet = await create_pet(db, pet, current_user.userid)
    return PetCreateResponse(pet_id=new_pet.petid, message="반려동물이 등록되었습니다.")


# 보관함 목록 — 숨김 처리된 반려동물(복원/영구삭제 화면용).
# ⚠️ 라우트 순서: "/archived" 는 "/{pet_id}" 보다 먼저 선언해야 한다(아니면 pet_id로 매칭).
@router.get("/archived", response_model=list[PetListResponse], status_code=200)
async def get_archived_pets(
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)
):
    pets = await get_archived_pets_by_userid(db, current_user.userid)
    return [
        PetListResponse(
            pet_id=pet.petid,
            petname=pet.petname,
            species=pet.species,
            breed=pet.breed,
            gender=pet.gender,
            profile_image=pet.profile_image,
        )
        for pet in pets
    ]


@router.get("/{pet_id}", response_model=PetDetailResponse, status_code=200)
async def get_pet(
    pet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    if pet.is_neutered is True:
        is_neutered_label = "예"
    elif pet.is_neutered is False:
        is_neutered_label = "아니오"
    else:
        is_neutered_label = "모름"

    return PetDetailResponse(
        pet_id=pet.petid,
        petname=pet.petname,
        species=pet.species,
        breed=pet.breed,
        gender=pet.gender,
        is_neutered=is_neutered_label,
        birth_date=str(pet.birth_date) if pet.birth_date else None,
        is_birth_unknown=pet.birth_date is None,
        checkup_date=str(pet.checkup_date) if pet.checkup_date else None,
        is_checkup_unknown=pet.checkup_date is None,
        weight_kg=float(pet.weight_kg) if pet.weight_kg else None,
        notes=pet.notes,
        profile_image=pet.profile_image,
        original_image=pet.original_image,
        doodle_strokes=pet.doodle_strokes,
    )


@router.put("/{pet_id}", response_model=MessageResponse, status_code=200)
async def modify_pet(
    pet_id: int,
    pet_data: PetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")
    if pet.userid != current_user.userid:
        raise HTTPException(status_code=403, detail="수정 권한이 없습니다.")

    await update_pet(db, pet, pet_data)
    return MessageResponse(message="반려동물 정보가 수정되었습니다.")


# 기본 '삭제' = 보관(숨김). 곧장 지우지 않고 보관함으로 옮긴다.
# 기본 목록·채팅 시작·신규 예약에서 제외되며, 보관함에서 복원할 수 있다.
@router.delete("/{pet_id}", response_model=MessageResponse, status_code=200)
async def archive_pet_endpoint(
    pet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    await archive_pet(db, pet)
    return MessageResponse(message="반려동물을 보관함으로 옮겼어요. 보관함에서 언제든 다시 꺼낼 수 있어요.")


# 보관 해제(복원) — 보관함의 반려동물을 다시 기본 목록으로.
@router.post("/{pet_id}/restore", response_model=MessageResponse, status_code=200)
async def restore_pet_endpoint(
    pet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid, include_archived=True)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    await restore_pet(db, pet)
    return MessageResponse(message="반려동물을 다시 목록으로 복원했어요.")


# 영구 삭제 — 보관함에서만, 연결된 진료/상담 기록이 전혀 없을 때만 실제로 지운다.
# 기록이 있으면 병원 보관 정책상 펫 행을 지울 수 없으므로 409로 안내하고 보관 상태를 유지한다.
@router.delete("/{pet_id}/permanent", response_model=MessageResponse, status_code=200)
async def permanently_delete_pet_endpoint(
    pet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid, include_archived=True)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")
    if pet.archived_at is None:
        raise HTTPException(status_code=400, detail="먼저 보관함으로 옮긴 뒤 영구 삭제할 수 있어요.")
    if await pet_has_records(db, pet_id):
        raise HTTPException(
            status_code=409,
            detail=(
                "상담·예약·진료 기록이 있는 반려동물은 영구 삭제할 수 없어요. "
                "진료부 등 병원 진료 기록은 수의사법 및 같은 법 시행규칙에 따라 "
                "일정 기간 보존될 수 있어요."
            ),
        )

    await hard_delete_pet(db, pet)
    return MessageResponse(message="반려동물 정보를 영구 삭제했어요.")
