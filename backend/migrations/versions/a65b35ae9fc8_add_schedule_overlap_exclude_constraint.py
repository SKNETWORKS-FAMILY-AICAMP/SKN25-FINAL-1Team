"""add schedule overlap exclude constraint

Revision ID: a65b35ae9fc8
Revises: 9c2269ea2bfb
Create Date: 2026-06-08 04:30:41.488867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a65b35ae9fc8'
down_revision: Union[str, None] = '9c2269ea2bfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # 모델(create_all)이 빈 DB 에서 이미 이 제약을 만들 수 있으므로 멱등 처리:
    # 먼저 DROP IF EXISTS 후 표준 DDL 로 재생성한다.
    op.execute('ALTER TABLE "scheduleDB" DROP CONSTRAINT IF EXISTS no_overlap_schedule')
    op.execute("""
        ALTER TABLE "scheduleDB"
        ADD CONSTRAINT no_overlap_schedule
        EXCLUDE USING gist (
            doctorid WITH =,
            tstzrange(confirmed_time, confirmed_end_time, '[)') WITH &&
        ) WHERE (
            deleted_at IS NULL
            AND status != 'CANCELLED'
            AND confirmed_time IS NOT NULL
            AND confirmed_end_time IS NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute('ALTER TABLE "scheduleDB" DROP CONSTRAINT IF EXISTS no_overlap_schedule')
