from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class ContactInquiry(Base):
    __tablename__ = "contact_inquiryDB"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String, nullable=False)
    phone       = Column(String, nullable=False)
    email       = Column(String, nullable=False)
    user_type   = Column(String, nullable=False)
    message     = Column(Text, nullable=False)
    is_replied  = Column(Boolean, nullable=False, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
