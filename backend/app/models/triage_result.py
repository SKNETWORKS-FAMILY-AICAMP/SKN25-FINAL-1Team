from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

class TriageResult(Base):
    __tablename__ = "triage_resultDB"

    id = Column(Integer, primary_key=True, autoincrement=True)
    emrid = Column(Integer, ForeignKey("guardianDB.emrid"), nullable=False)
    urgency_level = Column(String, nullable=False)
    urgency_level_num = Column(Integer, nullable=False)
    vtl_basis = Column(Text, nullable=True)            # 추론 근거(CoT)
    red_flags = Column(JSON, nullable=True)            # 매칭된 RED 디스크리미네이터 라벨 목록
    chief_complaint = Column(String, nullable=True)
    symptom_onset = Column(String, nullable=True)      # 발병 시점(참고 정보, 점수 아님)
    symptom_keywords = Column(JSON, nullable=True)
    suspected_diseases = Column(JSON, nullable=True)
    symptom_summary = Column(Text, nullable=True)
    recommended_action = Column(String, nullable=True)
    # 디스크리미네이터 판정 트레이스/추출 사실/이미지 근거 (감사·평가용)
    matched_discriminators = Column(JSON, nullable=True)  # [{section,label,urgency}]
    extracted_variables = Column(JSON, nullable=True)     # {섹션:{변수:값}}
    vision_evidence = Column(JSON, nullable=True)         # {region,cnn,vlm_description}
    rag_context = Column(JSON, nullable=True)             # 문진 단계 RAG 유사사례(차트가 재사용)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)