from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class DoctorProfile(Base):
    """원장 공개 콘텐츠 (보호자 원장 소개 노출). 수의사웹/발행에서 채운다."""
    __tablename__ = "doctor_profileDB"

    doctorid          = Column(Integer, ForeignKey("doctorDB.doctorid"), primary_key=True)
    specialty         = Column(String, nullable=True)   # 전문 진료
    education         = Column(String, nullable=True)    # 학력
    bio               = Column(Text, nullable=True)      # 소개글
    specialty_areas   = Column(JSON, nullable=True)      # list[str] 전문 분야
    profile_image_url = Column(Text, nullable=True)      # S3 URL
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
