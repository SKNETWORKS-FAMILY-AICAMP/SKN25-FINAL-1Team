"""add orch_state to chat_historyDB (v2 오케스트레이터 대화 상태)

Revision ID: p1a2b3c4d5e6
Revises: o1a2b3c4d5e6
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p1a2b3c4d5e6"
down_revision: Union[str, None] = "o1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("chat_historyDB")}
    if "orch_state" not in columns:
        op.add_column("chat_historyDB", sa.Column("orch_state", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_historyDB", "orch_state")
