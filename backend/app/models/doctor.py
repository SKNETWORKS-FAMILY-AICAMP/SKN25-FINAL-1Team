from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

class Doctor(Base):
    __tablename__ = "doctorDB"

    doctorid       = Column(Integer, primary_key=True, autoincrement=True)
    hospitalid     = Column(Integer, ForeignKey("hospitalDB.hospitalid"), nullable=True)
    doctor_name    = Column(String, nullable=False)
    license_number = Column(String, nullable=True)
    email          = Column(String, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
