from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class ClinicSignupRequest(Base):
    """입점 신청 원본 + 검토 상태. 운영팀이 검토 후 '발행'하면 병원/원장/계정 생성."""
    __tablename__ = "clinic_signup_requestDB"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    # 신원·계정
    hospital_name        = Column(String, nullable=False)
    business_number      = Column(String, nullable=False)
    business_license_url = Column(Text, nullable=True)
    hospital_phone       = Column(String, nullable=True)
    hospital_address     = Column(String, nullable=True)
    owner_email          = Column(String, nullable=True)
    desired_loginid      = Column(String, nullable=False)
    # 공개 콘텐츠
    tagline              = Column(String, nullable=True)
    intro                = Column(Text, nullable=True)
    features             = Column(JSON, nullable=True)   # list[str]
    banner_image_url     = Column(Text, nullable=True)
    hours                = Column(JSON, nullable=True)    # OperatingHours
    doctors              = Column(JSON, nullable=True)    # list[DoctorApplication]
    # 메타
    status               = Column(String, nullable=False, server_default="접수")
    reject_reason        = Column(Text, nullable=True)
    created_hospitalid   = Column(Integer, ForeignKey("hospitalDB.hospitalid"), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at          = Column(DateTime(timezone=True), nullable=True)
