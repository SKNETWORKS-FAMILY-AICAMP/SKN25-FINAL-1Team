"""drop unique constraint on hospitalDB.business_number

Revision ID: k1a2b3c4d5e6
Revises: j1b2c3d4e5f6
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'k1a2b3c4d5e6'
down_revision: Union[str, None] = 'j1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('hospitalDB_business_number_key', 'hospitalDB', type_='unique')


def downgrade() -> None:
    op.create_unique_constraint('hospitalDB_business_number_key', 'hospitalDB', ['business_number'])
