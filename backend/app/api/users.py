from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.security import verify_password, hash_password
from app.schemas.user import UserProfileResponse, UpdateProfileRequest, ChangePasswordRequest
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user=Depends(get_current_user)):
    return UserProfileResponse(
        name=current_user.name,
        phone=current_user.phone,
        created_at=str(current_user.created_at.date()),
    )


@router.put("/me", response_model=MessageResponse)
async def update_my_profile(
    request: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if request.name:
        current_user.name = request.name
    if request.phone:
        current_user.phone = request.phone
    await db.commit()
    return MessageResponse(message="회원 정보가 수정되었습니다.")


@router.put("/me/password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not verify_password(request.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
    if request.new_password != request.new_password_confirm:
        raise HTTPException(status_code=400, detail="새 비밀번호가 일치하지 않습니다.")
    current_user.password = hash_password(request.new_password)
    await db.commit()
    return MessageResponse(message="비밀번호가 변경되었습니다.")
