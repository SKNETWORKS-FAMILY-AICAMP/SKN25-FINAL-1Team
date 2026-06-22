from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, literal_column
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.sql import func, text
from app.db.base import Base

class Schedule(Base):
    __tablename__ = "scheduleDB"

    scheduleid = Column(Integer, primary_key=True, autoincrement=True)
    emrid = Column(Integer, ForeignKey("guardianDB.emrid"), nullable=False)
    doctorid = Column(Integer, ForeignKey("doctorDB.doctorid"), nullable=False)
    duration_min = Column(Integer, nullable=False)
    confirmed_time = Column(DateTime(timezone=True), nullable=True)
    confirmed_end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="예약대기")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    # 소프트 삭제(의료 데이터): NULL = 활성, 값이 있으면 삭제된 시각
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # 동일 원장·동일 시작시각 중복 차단(부분 유니크 인덱스).
        # 마이그레이션 9c2269ea2bfb 와 짝(IF NOT EXISTS 로 멱등).
        Index(
            "uq_schedule_doctor_time",
            "doctorid",
            "confirmed_time",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status != 'CANCELLED'"),
        ),
        # 동일 원장의 진료 시간대 '겹침' 차단(GiST EXCLUDE, btree_gist 필요).
        # 마이그레이션 a65b35ae9fc8 와 짝(DROP IF EXISTS 후 ADD 로 멱등).
        # btree_gist 확장은 0001 / a65b35 에서 생성됨.
        ExcludeConstraint(
            (literal_column("doctorid"), "="),
            (literal_column("tstzrange(confirmed_time, confirmed_end_time, '[)')"), "&&"),
            name="no_overlap_schedule",
            using="gist",
            where=text(
                "deleted_at IS NULL AND status != 'CANCELLED' "
                "AND confirmed_time IS NOT NULL AND confirmed_end_time IS NOT NULL"
            ),
        ),
    )

