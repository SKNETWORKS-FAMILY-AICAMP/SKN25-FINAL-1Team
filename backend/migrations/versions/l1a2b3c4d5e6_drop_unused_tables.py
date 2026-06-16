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
    op.drop_table('photo_analysisDB')
    op.drop_table('agent_pipeline_resultDB')


def downgrade() -> None:
    pass
