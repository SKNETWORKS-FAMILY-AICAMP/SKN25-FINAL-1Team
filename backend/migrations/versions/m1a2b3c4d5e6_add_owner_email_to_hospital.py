"""add owner_email to hospitalDB

Revision ID: m1a2b3c4d5e6
Revises: l1a2b3c4d5e6
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'm1a2b3c4d5e6'
down_revision: Union[str, None] = 'hosp_is_active'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hospitalDB', sa.Column('owner_email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('hospitalDB', 'owner_email')
