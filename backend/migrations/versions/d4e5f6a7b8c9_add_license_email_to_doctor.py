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
    op.add_column('doctorDB', sa.Column('license_number', sa.String(), nullable=True))
    op.add_column('doctorDB', sa.Column('email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('doctorDB', 'email')
    op.drop_column('doctorDB', 'license_number')
