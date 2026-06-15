from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class AdminUser(Base):
    """운영팀 계정. 입점 신청 검토/발행, 모니터링 접근."""
    __tablename__ = "admin_userDB"

    adminid    = Column(Integer, primary_key=True, autoincrement=True)
    loginid    = Column(String, nullable=False, unique=True)
    password   = Column(String, nullable=False)
    name       = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
