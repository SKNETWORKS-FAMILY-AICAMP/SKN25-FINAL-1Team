"""extend vet_schedule for weekly template and date-specific closures

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE "vet_scheduleDB" ADD COLUMN IF NOT EXISTS day_of_week INTEGER')
    op.execute('ALTER TABLE "vet_scheduleDB" ADD COLUMN IF NOT EXISTS is_open BOOLEAN NOT NULL DEFAULT TRUE')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN date DROP NOT NULL')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN start_time DROP NOT NULL')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN end_time DROP NOT NULL')
    # 주간 템플릿: (doctorid, day_of_week) 유니크
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_vet_schedule_doctor_dow '
        'ON "vet_scheduleDB" (doctorid, day_of_week) '
        'WHERE day_of_week IS NOT NULL'
    )
    # 특정날짜 레코드: (doctorid, date) 유니크
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_vet_schedule_doctor_date '
        'ON "vet_scheduleDB" (doctorid, date) '
        'WHERE date IS NOT NULL'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_vet_schedule_doctor_dow')
    op.execute('DROP INDEX IF EXISTS uq_vet_schedule_doctor_date')
    op.execute('ALTER TABLE "vet_scheduleDB" DROP COLUMN IF EXISTS is_open')
    op.execute('ALTER TABLE "vet_scheduleDB" DROP COLUMN IF EXISTS day_of_week')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN date SET NOT NULL')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN start_time SET NOT NULL')
    op.execute('ALTER TABLE "vet_scheduleDB" ALTER COLUMN end_time SET NOT NULL')
