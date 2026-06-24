from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Boolean, Text, ForeignKey
from app.db.base import Base

class Pet(Base):
    __tablename__ = "petDB"

    petid = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(Integer, ForeignKey("userDB.userid"), nullable=False)
    # 보관/숨김: 보호자가 목록에서 숨긴(보관함으로 옮긴) 반려동물. NULL = 활성, 값 = 보관 시각.
    # 하드 삭제가 아니므로 상담·예약·EMR·처방·문진 기록과 FK 무결성/이력이 그대로 유지된다.
    # (영구 삭제는 보관함에서, 연결 기록이 전혀 없을 때만 별도 수행 — crud.hard_delete_pet)
    archived_at = Column(DateTime(timezone=True), nullable=True)
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