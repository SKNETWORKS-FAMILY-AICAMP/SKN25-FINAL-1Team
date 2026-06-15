from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_user import AdminUser


async def get_admin_by_loginid(db: AsyncSession, loginid: str):
    result = await db.execute(select(AdminUser).where(AdminUser.loginid == loginid))
    return result.scalar_one_or_none()
