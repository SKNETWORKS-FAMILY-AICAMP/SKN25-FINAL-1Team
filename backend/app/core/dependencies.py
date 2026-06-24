from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.config import settings

from app.models.hospital import Hospital
from app.models.user import User
from app.models.admin_user import AdminUser

security = HTTPBearer()

# 수의사(병원) 인증
async def get_current_hospital(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        hospital_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if hospital_id is None or token_type != "hospital":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        # sub 가 숫자가 아니면 ValueError → 401 로 처리(500 누출 방지).
        hospital_pk = int(hospital_id)

    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    hospital = await db.get(Hospital, hospital_pk)

    if hospital is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return hospital

# 보호자 인증
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "user":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        # sub 가 숫자가 아니면 ValueError → 401 로 처리(500 누출 방지).
        user_pk = int(user_id)

    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    result = await db.execute(
        select(User).where(User.userid == user_pk)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user

# 운영자(admin) 인증
async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        admin_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if admin_id is None or token_type != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        # sub 가 숫자가 아니면 ValueError → 401 로 처리(500 누출 방지).
        admin_pk = int(admin_id)

    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    admin = await db.get(AdminUser, admin_pk)

    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return admin
