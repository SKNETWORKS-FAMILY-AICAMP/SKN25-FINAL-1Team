"""triage_resultDB: 디스크리미네이터 컬럼 추가 + 미사용 컬럼 제거

추가: matched_discriminators, extracted_variables, vision_evidence (JSON)
제거: need_photo, need_followup, followup_reason

Revision ID: q1a2b3c4d5e6
Revises: p1a2b3c4d5e6
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q1a2b3c4d5e6"
down_revision: Union[str, None] = "p1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "triage_resultDB"
_ADD = ["matched_discriminators", "extracted_variables", "vision_evidence"]
_DROP = ["need_photo", "need_followup", "followup_reason"]


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    for name in _ADD:
        if name not in columns:
            op.add_column(_TABLE, sa.Column(name, sa.JSON(), nullable=True))
    for name in _DROP:
        if name in columns:
            op.drop_column(_TABLE, name)


def downgrade() -> None:
    columns = _columns()
    # 되돌리기: 추가분 제거 + 제거분 복원(원래 타입)
    for name in _ADD:
        if name in columns:
            op.drop_column(_TABLE, name)
    if "need_photo" not in columns:
        op.add_column(_TABLE, sa.Column("need_photo", sa.Boolean(), nullable=True))
    if "need_followup" not in columns:
        op.add_column(_TABLE, sa.Column("need_followup", sa.Boolean(), nullable=True))
    if "followup_reason" not in columns:
        op.add_column(_TABLE, sa.Column("followup_reason", sa.String(), nullable=True))
