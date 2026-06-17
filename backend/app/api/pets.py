from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.pet import PetCreate, PetListResponse, PetDetailResponse, PetUpdate, PetCreateResponse
from app.schemas.common import MessageResponse
from app.crud.pet import create_pet, get_pets_by_userid, get_pet_by_id, update_pet, delete_pet
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


@router.delete("/{pet_id}", response_model=MessageResponse, status_code=200)
async def remove_pet(
    pet_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    pet = await get_pet_by_id(db, pet_id, current_user.userid)
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    await delete_pet(db, pet)
    return MessageResponse(message="반려동물이 삭제되었습니다.")
