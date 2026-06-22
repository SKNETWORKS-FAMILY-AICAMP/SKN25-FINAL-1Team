from sqlalchemy import Column, DateTime, Index, Integer, String, Text
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

    __table_args__ = (
        # pgvector 코사인 유사도용 HNSW 인덱스. 마이그레이션 160babc12a3f 가 DB 에 생성하며,
        # 모델에도 선언해 두어 autogenerate 가 이 인덱스를 drop 대상으로 오인하지 않게 한다.
        # (triage_rag_documents 는 0001 의 _EXCLUDE 라 create_all 단계에선 만들어지지 않는다.)
        Index(
            "ix_triage_rag_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
