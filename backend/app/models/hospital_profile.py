from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class HospitalProfile(Base):
    """병원 공개 콘텐츠 (보호자 병원탭 노출). 운영팀이 입점 발행 시 채운다."""
    __tablename__ = "hospital_profileDB"

    hospitalid       = Column(Integer, ForeignKey("hospitalDB.hospitalid"), primary_key=True)
    tagline          = Column(String, nullable=True)   # 한 줄 소개
    intro            = Column(Text, nullable=True)      # 소개 본문
    banner_image_url = Column(Text, nullable=True)      # S3 URL
    features         = Column(JSON, nullable=True)      # list[str] 병원 특징 태그
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
