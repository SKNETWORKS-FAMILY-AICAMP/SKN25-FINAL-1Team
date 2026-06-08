"""add need_followup and followup_reason to triage_result

Revision ID: b1f4c7d2e8a9
Revises: a65b35ae9fc8
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1f4c7d2e8a9"
down_revision: Union[str, None] = "a65b35ae9fc8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("triage_resultDB")
    }

    if "need_followup" not in existing_columns:
        op.add_column("triage_resultDB", sa.Column("need_followup", sa.Boolean(), nullable=True))
    if "followup_reason" not in existing_columns:
        op.add_column("triage_resultDB", sa.Column("followup_reason", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("triage_resultDB")
    }

    if "followup_reason" in existing_columns:
        op.drop_column("triage_resultDB", "followup_reason")
    if "need_followup" in existing_columns:
        op.drop_column("triage_resultDB", "need_followup")
