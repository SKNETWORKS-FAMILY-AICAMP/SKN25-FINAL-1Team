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
from app.models.vet_schedule import VetSchedule  # noqa: F401


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # triage_rag_documents 는 다음 마이그레이션(160babc)이 vector 확장과 함께 생성한다.
    # env.py 가 해당 모델을 import 하므로 Base.metadata 에는 포함되지만, 여기서 만들면:
    #   1) 이 시점엔 vector 확장이 없어 VECTOR 컬럼 생성이 'type "vector" does not exist' 로 실패
    #   2) 설령 만들어도 160babc 의 create_table 과 'already exists' 충돌
    # → 빈 DB 셋업이 통째로 깨지므로 0001 에서는 제외하고 160babc 에 맡긴다.
    tables = [t for t in Base.metadata.sorted_tables if t.name != "triage_rag_documents"]
    Base.metadata.create_all(bind=bind, tables=tables)

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
