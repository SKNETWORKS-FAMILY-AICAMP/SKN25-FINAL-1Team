"""add is_active to hospitalDB (폐업 소프트 처리)

Revision ID: hosp_is_active
Revises: hosp_img_positions
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "hosp_is_active"
down_revision: Union[str, None] = "hosp_img_positions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("hospitalDB")}
    if "is_active" not in cols:
        op.add_column(
            "hospitalDB",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("hospitalDB")}
    if "is_active" in cols:
        op.drop_column("hospitalDB", "is_active")
