"""triage_resultDB: rag_context 컬럼 추가 (문진 단계 RAG 결과, 차트 재사용)

Revision ID: r1a2b3c4d5e6
Revises: q1a2b3c4d5e6
Create Date: 2026-06-19 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r1a2b3c4d5e6"
down_revision: Union[str, None] = "q1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "triage_resultDB"
_COL = "rag_context"


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    if _COL not in _columns():
        op.add_column(_TABLE, sa.Column(_COL, sa.JSON(), nullable=True))


def downgrade() -> None:
    if _COL in _columns():
        op.drop_column(_TABLE, _COL)
