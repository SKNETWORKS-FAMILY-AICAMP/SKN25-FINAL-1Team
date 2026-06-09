"""add license_number and email to doctorDB

Revision ID: d4e5f6a7b8c9
Revises: b1f4c7d2e8a9
Create Date: 2026-06-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b1f4c7d2e8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0001 의 Base.metadata.create_all 은 '현재 모델' 기준으로 doctorDB 를 만든다.
    # doctor 모델에 license_number/email 이 이미 있으면 0001 단계에서 컬럼이 생성되므로,
    # 여기서 무조건 add_column 하면 'DuplicateColumn' 으로 전체 upgrade 가 롤백된다.
    # → 존재 여부를 가드해 멱등하게 둔다(빈 DB·구 DB 양쪽 안전). 패턴: b1f4c7d2e8a9.
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("doctorDB")
    }

    if "license_number" not in existing_columns:
        op.add_column('doctorDB', sa.Column('license_number', sa.String(), nullable=True))
    if "email" not in existing_columns:
        op.add_column('doctorDB', sa.Column('email', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("doctorDB")
    }

    if "email" in existing_columns:
        op.drop_column('doctorDB', 'email')
    if "license_number" in existing_columns:
        op.drop_column('doctorDB', 'license_number')
