"""add contact_inquiryDB table

Revision ID: n1a2b3c4d5e6
Revises: m1a2b3c4d5e6
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'n1a2b3c4d5e6'
down_revision: Union[str, None] = 'm1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contact_inquiryDB',
        sa.Column('id',         sa.Integer(),                                    nullable=False),
        sa.Column('name',       sa.String(),                                     nullable=False),
        sa.Column('phone',      sa.String(),                                     nullable=False),
        sa.Column('email',      sa.String(),                                     nullable=False),
        sa.Column('user_type',  sa.String(),                                     nullable=False),
        sa.Column('message',    sa.Text(),                                       nullable=False),
        sa.Column('is_replied', sa.Boolean(),                                    nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('contact_inquiryDB')
