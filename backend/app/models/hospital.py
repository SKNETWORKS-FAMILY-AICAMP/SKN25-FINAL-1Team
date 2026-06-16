from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class Hospital(Base):
    __tablename__ = "hospitalDB"

    hospitalid          = Column(Integer, primary_key=True, autoincrement=True)
    hospital_name       = Column(String, nullable=False)
    hospital_address    = Column(String, nullable=True)
    hospital_number     = Column(String, nullable=True)
    business_number     = Column(String, nullable=False)
    loginid             = Column(String, nullable=False, unique=True)
    password            = Column(String, nullable=False)
    is_initial_password = Column(Boolean, nullable=False, default=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
