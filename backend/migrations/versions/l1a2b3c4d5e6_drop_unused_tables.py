"""drop unused tables: photo_analysisDB, agent_pipeline_resultDB

Revision ID: l1a2b3c4d5e6
Revises: k1a2b3c4d5e6
Create Date: 2026-06-16

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'l1a2b3c4d5e6'
down_revision: Union[str, None] = 'k1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF EXISTS 로 멱등 처리: 모델/0001 에서 두 테이블 정의를 제거했으므로
    # 빈 DB 에서는 애초에 생성되지 않는다. 기존 DB 에서는 그대로 드롭된다.
    op.execute('DROP TABLE IF EXISTS "photo_analysisDB"')
    op.execute('DROP TABLE IF EXISTS "agent_pipeline_resultDB"')


def downgrade() -> None:
    pass
