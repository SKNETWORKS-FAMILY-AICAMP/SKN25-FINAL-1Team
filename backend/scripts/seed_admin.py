"""운영자(admin) 계정 시드 스크립트.

사용법:
  cd backend
  DATABASE_URL=postgresql://medipaw:medipaw_secret@localhost:5432/medipaw \
    python scripts/seed_admin.py

생성 계정(이미 있으면 비밀번호만 갱신):
  운영자(admin): admin / Admin1234!
환경변수로 변경 가능: ADMIN_LOGINID, ADMIN_PASSWORD, ADMIN_NAME
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://medipaw:medipaw_secret@localhost:5432/medipaw")
ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://").replace("postgresql+psycopg2://", "postgresql+asyncpg://")

from app.core.security import hash_password
from app.models.admin_user import AdminUser

LOGINID = os.environ.get("ADMIN_LOGINID", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin1234!")
NAME = os.environ.get("ADMIN_NAME", "운영자")


async def main():
    engine = create_async_engine(ASYNC_URL, echo=False, connect_args={"statement_cache_size": 0})
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.loginid == LOGINID))
        admin = result.scalar_one_or_none()
        if admin:
            admin.password = hash_password(PASSWORD)
            admin.name = NAME
            print(f"[seed_admin] 기존 운영자 비밀번호 갱신: {LOGINID}")
        else:
            db.add(AdminUser(loginid=LOGINID, password=hash_password(PASSWORD), name=NAME))
            print(f"[seed_admin] 운영자 생성: {LOGINID} / {PASSWORD}")
        await db.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
