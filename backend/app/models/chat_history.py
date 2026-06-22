from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

class ChatHistory(Base):
    __tablename__ = "chat_historyDB"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(Integer, ForeignKey("userDB.userid"), nullable=False)
    petid = Column(Integer, ForeignKey("petDB.petid"), nullable=False)
    emrid = Column(Integer, ForeignKey("guardianDB.emrid"), nullable=True)
    messages = Column(JSON, nullable=True, default=[])
    keywords = Column(JSON, nullable=True, default=[])
    title = Column(String, nullable=True)  # 문진 완료 시 LLM이 생성한 대화 요약 제목(목록 표시용)
    # v2 오케스트레이터 대화 상태(국면/흐름/문진진행/경과요약). 신규.
    orch_state = Column(JSON, nullable=True)
    is_complete = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)