"""add is_active to doctorDB

Revision ID: hosp_doctor_is_active
Revises: l1a2b3c4d5e6
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "hosp_doctor_is_active"
down_revision: Union[str, None] = "l1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0001 의 create_all 이 '현재 모델' 기준으로 doctorDB 를 만들 수 있어, is_active 가
    # 이미 있으면 중복 add 로 전체 upgrade 가 롤백된다 → 존재 가드로 멱등 처리(패턴: d4e5f6a7b8c9).
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("doctorDB")
    }

    if "is_active" not in existing_columns:
        op.add_column(
            "doctorDB",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("doctorDB")
    }

    if "is_active" in existing_columns:
        op.drop_column("doctorDB", "is_active")
