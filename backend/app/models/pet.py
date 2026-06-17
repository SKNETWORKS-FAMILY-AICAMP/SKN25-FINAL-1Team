from sqlalchemy import Column, Integer, String, Date, Numeric, Boolean, Text, ForeignKey
from app.db.base import Base

class Pet(Base):
    __tablename__ = "petDB"

    petid = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(Integer, ForeignKey("userDB.userid"), nullable=False)
    profile_image = Column(String, nullable=True)
    # 사진 꾸미기 비파괴 편집용: 그림 입히기 전 원본 사진 URL + 그림 stroke(JSON).
    # profile_image는 표시용 합성본, 이 둘은 재편집을 위한 원천 데이터다.
    original_image = Column(String, nullable=True)
    doodle_strokes = Column(Text, nullable=True)
    species = Column(String, nullable=True)
    breed = Column(String, nullable=True)
    petname = Column(String, nullable=False)
    gender = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    checkup_date = Column(Date, nullable=True)
    weight_kg = Column(Numeric, nullable=True)
    is_neutered = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)