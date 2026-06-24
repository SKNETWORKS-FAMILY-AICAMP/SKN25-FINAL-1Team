from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pet import Pet
from app.schemas.pet import PetCreate, PetUpdate

# 반려동물 등록
async def create_pet(db: AsyncSession, pet: PetCreate, userid: int):
    db_pet = Pet(
        userid=userid,
        petname=pet.petname,
        species=pet.species,
        breed=pet.breed,
        gender=pet.gender,
        is_neutered=True if pet.is_neutered == "예" else False if pet.is_neutered in ("아니오", "아니요") else None,
        birth_date=None if pet.is_birth_unknown else pet.birth_date,
        checkup_date=None if pet.is_checkup_unknown else pet.checkup_date,
        weight_kg=pet.weight_kg,
        notes=pet.notes,
        profile_image=pet.profile_image,
        original_image=pet.original_image,
        doodle_strokes=pet.doodle_strokes,
    )
    db.add(db_pet)
    await db.commit()
    await db.refresh(db_pet)
    return db_pet

# 반려동물 기본 목록 조회 (보호자 화면 — 보관(숨김)된 펫 제외)
async def get_pets_by_userid(db: AsyncSession, userid: int):
    result = await db.execute(
        select(Pet).where(Pet.userid == userid, Pet.archived_at.is_(None))
    )
    return result.scalars().all()

# 보관함 목록 조회 (숨김 처리된 펫만 — 복원/영구삭제 화면용)
async def get_archived_pets_by_userid(db: AsyncSession, userid: int):
    result = await db.execute(
        select(Pet)
        .where(Pet.userid == userid, Pet.archived_at.isnot(None))
        .order_by(Pet.archived_at.desc())
    )
    return result.scalars().all()

# 반려동물 상세 조회
#   include_archived=False(기본): 활성 펫만 — 일반 상세/수정/보관 진입점.
#   include_archived=True       : 보관된 펫도 포함 — 복원/영구삭제 진입점.
async def get_pet_by_id(
    db: AsyncSession, pet_id: int, userid: int, *, include_archived: bool = False
):
    conds = [Pet.petid == pet_id, Pet.userid == userid]
    if not include_archived:
        conds.append(Pet.archived_at.is_(None))
    result = await db.execute(select(Pet).where(*conds))
    return result.scalar_one_or_none()

# 반려동물 수정
async def update_pet(db: AsyncSession, pet: Pet, pet_data: PetUpdate):
    if pet_data.petname is not None:
        pet.petname = pet_data.petname
    if pet_data.species is not None:
        pet.species = pet_data.species
    if pet_data.breed is not None:
        pet.breed = pet_data.breed
    if pet_data.gender is not None:
        pet.gender = pet_data.gender
    if pet_data.is_neutered is not None:
        pet.is_neutered = True if pet_data.is_neutered == "예" else False if pet_data.is_neutered in ("아니오", "아니요") else None
    if pet_data.is_birth_unknown == True:
        pet.birth_date = None
    elif pet_data.birth_date is not None:
        pet.birth_date = pet_data.birth_date

    if pet_data.is_checkup_unknown == True:
        pet.checkup_date = None
    elif pet_data.checkup_date is not None:
        pet.checkup_date = pet_data.checkup_date
    if pet_data.weight_kg is not None:
        pet.weight_kg = pet_data.weight_kg
    if pet_data.notes is not None:
        pet.notes = pet_data.notes
    if pet_data.profile_image is not None:
        pet.profile_image = pet_data.profile_image
    if pet_data.original_image is not None:
        pet.original_image = pet_data.original_image
    if pet_data.doodle_strokes is not None:
        pet.doodle_strokes = pet_data.doodle_strokes

    await db.commit()
    await db.refresh(pet)
    return pet

# 반려동물 보관(숨김) — 기본 '삭제' 동작.
# 하드 삭제하면 chat_history/guardian/emr 등 자식 기록이 FK 위반을 일으키고 이력이 사라진다.
# 사망 등으로 보이지 않게 하고 싶어도 진료 기록은 남겨야 하므로, archived_at 으로 숨기기만 한다.
async def archive_pet(db: AsyncSession, pet: Pet):
    if pet.archived_at is None:
        pet.archived_at = datetime.now(timezone.utc)
        db.add(pet)
        await db.commit()


# 보관 해제(복원) — 보관함에서 다시 활성 목록으로.
async def restore_pet(db: AsyncSession, pet: Pet):
    if pet.archived_at is not None:
        pet.archived_at = None
        db.add(pet)
        await db.commit()


# 연결된 진료/상담 기록 존재 여부 — 영구 삭제 가능 여부 판정용.
# 하나라도 있으면(상담/예약-guardian/진료-EMR) 보관 정책상 펫 행을 지울 수 없다(이력 보존).
async def pet_has_records(db: AsyncSession, petid: int) -> bool:
    from app.models.chat_history import ChatHistory
    from app.models.emr import EMR
    from app.models.guardian import Guardian

    for model in (ChatHistory, Guardian, EMR):
        exists = (
            await db.execute(select(model.petid).where(model.petid == petid).limit(1))
        ).first()
        if exists is not None:
            return True
    return False


# 영구 삭제 — 보관함에서만, 연결된 기록이 전혀 없을 때만(실수로 등록한 펫 정리용).
# 기록이 있으면 호출 전에 pet_has_records 로 막아야 한다(FK 위반/이력 손실 방지).
async def hard_delete_pet(db: AsyncSession, pet: Pet):
    await db.delete(pet)
    await db.commit()
