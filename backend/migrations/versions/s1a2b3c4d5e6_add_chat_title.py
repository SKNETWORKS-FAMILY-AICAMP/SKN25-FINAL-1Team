"""chat_historyDB: title 컬럼 추가 (문진 완료 시 LLM 생성 요약 제목)

Revision ID: s1a2b3c4d5e6
Revises: r1a2b3c4d5e6
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s1a2b3c4d5e6"
down_revision: Union[str, None] = "r1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "chat_historyDB"
_COL = "title"


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    if _COL not in _columns():
        op.add_column(_TABLE, sa.Column(_COL, sa.String(), nullable=True))


def downgrade() -> None:
    if _COL in _columns():
        op.drop_column(_TABLE, _COL)
