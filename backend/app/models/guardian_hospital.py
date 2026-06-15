from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func, text
from app.db.base import Base


class GuardianHospital(Base):
    """보호자 ↔ 병원 M:N. is_primary = 기본(현재) 병원."""
    __tablename__ = "guardian_hospitalDB"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    userid     = Column(Integer, ForeignKey("userDB.userid"), nullable=False)
    hospitalid = Column(Integer, ForeignKey("hospitalDB.hospitalid"), nullable=False)
    is_primary = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("userid", "hospitalid", name="uq_guardian_hospital"),
    )
