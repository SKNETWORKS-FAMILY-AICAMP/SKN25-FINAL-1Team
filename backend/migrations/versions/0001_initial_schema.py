"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.base import Base

# Import all models so Base.metadata contains the full current schema.
from app.models.agent_pipeline_result import AgentPipelineResult  # noqa: F401
from app.models.alarm import DoctorAlarm  # noqa: F401
from app.models.chat_history import ChatHistory  # noqa: F401
from app.models.doctor import Doctor  # noqa: F401
from app.models.drug import Drug  # noqa: F401
from app.models.emr import EMR  # noqa: F401
from app.models.followup import Followup  # noqa: F401
from app.models.guardian import Guardian  # noqa: F401
from app.models.hospital import Hospital  # noqa: F401
from app.models.master import CategoryMaster, TriageMaster  # noqa: F401
from app.models.pet import Pet  # noqa: F401
from app.models.photo_analysis import PhotoAnalysis  # noqa: F401
from app.models.prescription import Prescription  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.schedule import Schedule  # noqa: F401
from app.models.triage_result import TriageResult  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.validation_result import ValidationResult  # noqa: F401
from app.models.vet_schedule import HospitalWeeklySchedule, HospitalClosedDate, VetWeeklySchedule  # noqa: F401


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 제외 목록:
    #   triage_rag_documents  → vector 확장이 없어 VECTOR 타입 생성 실패 (160babc 가 처리)
    #   hospital_weekly_scheduleDB / hospital_closed_datesDB / vet_weekly_scheduleDB
    #     → j1b2c3d4e5f6 에서 vet_scheduleDB 를 분리해 생성. 여기서 미리 만들면
    #       해당 마이그레이션과 'already exists' 충돌.
    _EXCLUDE = {
        "triage_rag_documents",
        "hospital_weekly_scheduleDB",
        "hospital_closed_datesDB",
        "vet_weekly_scheduleDB",
    }
    tables = [t for t in Base.metadata.sorted_tables if t.name not in _EXCLUDE]
    Base.metadata.create_all(bind=bind, tables=tables)

    # vet_scheduleDB 는 현재 모델에서 제거됐지만 9c2269ea2bfb ~ e7f8a9b0c1d2 가
    # ALTER TABLE 로 이 테이블을 수정하므로 빈 DB 에도 존재해야 한다.
    # 중간 마이그레이션이 추가할 컬럼을 미리 포함해두면 IF NOT EXISTS 덕분에 no-op 으로 통과.
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS "vet_scheduleDB" (
            vetscheduleid SERIAL PRIMARY KEY,
            doctorid      INTEGER NOT NULL REFERENCES "doctorDB"(doctorid),
            date          DATE,
            start_time    TIME,
            end_time      TIME,
            lunch_start   TIME,
            lunch_end     TIME,
            day_of_week   INTEGER,
            is_open       BOOLEAN NOT NULL DEFAULT TRUE
        )
    """))

    bind.execute(
        sa.text(
            """
            INSERT INTO "category_masterDB" (code, label) VALUES
              (1, '정기검진'),
              (2, '일반진료')
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO "triage_masterDB" (code, label) VALUES
              (1, '응급'),
              (2, '준응급'),
              (3, '일반')
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
