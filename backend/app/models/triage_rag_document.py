from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class TriageRagDocument(Base):
    __tablename__ = "triage_rag_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String, unique=True, nullable=False)
    department = Column(String, index=True, nullable=False)
    disease = Column(String, index=True, nullable=True)
    life_cycle = Column(String, index=True, nullable=True)
    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
