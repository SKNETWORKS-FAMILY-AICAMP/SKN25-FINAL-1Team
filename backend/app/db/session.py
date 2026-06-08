from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _to_async_url(url: str) -> str:
    """동기 PostgreSQL URL을 asyncpg 드라이버용 URL로 변환한다.

    alembic 마이그레이션은 settings.DATABASE_URL(psycopg2)을 그대로 쓰고,
    런타임 앱만 비동기 드라이버를 사용하도록 여기서만 변환한다.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_async_url = _to_async_url(settings.DATABASE_URL)

# statement_cache_size는 asyncpg 전용 인자다. SQLite(aiosqlite) 등 다른 드라이버에
# 그대로 넘기면 'unexpected keyword argument' 로 연결이 깨지므로 dialect별로 분기한다.
# (asyncpg: prepared statement 캐시 비활성화 → 마이그레이션 후 'cached plan' 오류 방지)
# ssl은 지정하지 않는다 → asyncpg 기본값(sslmode=prefer): RDS처럼 SSL을 요구하는
# 서버는 암호화로 붙고, 로컬 컨테이너는 평문으로 fallback 한다.
# (ssl=False 로 강제하면 RDS가 'no pg_hba.conf entry ... no encryption' 으로 거절함)
_connect_args = {"statement_cache_size": 0} if "+asyncpg" in _async_url else {}

engine = create_async_engine(
    _async_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# expire_on_commit=False: 커밋 후에도 ORM 속성 접근 시 재조회(await 필요)가
# 발생하지 않도록 하여 비동기 환경에서 안전하게 객체를 반환할 수 있게 한다.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as db:
        yield db
