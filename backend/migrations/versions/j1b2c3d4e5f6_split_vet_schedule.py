"""split vet_scheduleDB into hospital_weekly_scheduleDB, hospital_closed_datesDB, vet_weekly_scheduleDB

Revision ID: j1b2c3d4e5f6
Revises: i1a2b3c4d5e6
Create Date: 2026-06-15 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "j1b2c3d4e5f6"
down_revision: Union[str, None] = "i1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    existing = inspect(op.get_bind()).get_table_names()

    # 빈 DB(fresh/reset)에서는 0001 이 현재 모델 기준으로 이미 3개 테이블을 만들었을 수 있음.
    if "hospital_weekly_scheduleDB" not in existing:
        op.create_table(
            "hospital_weekly_scheduleDB",
            sa.Column("hospitalid", sa.Integer(), sa.ForeignKey("hospitalDB.hospitalid"), nullable=False),
            sa.Column("day_of_week", sa.Integer(), nullable=False),
            sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("lunch_start", sa.Time(), nullable=True),
            sa.Column("lunch_end", sa.Time(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("hospitalid", "day_of_week"),
        )

    if "hospital_closed_datesDB" not in existing:
        op.create_table(
            "hospital_closed_datesDB",
            sa.Column("hospitalid", sa.Integer(), sa.ForeignKey("hospitalDB.hospitalid"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("hospitalid", "date"),
        )

    if "vet_weekly_scheduleDB" not in existing:
        op.create_table(
            "vet_weekly_scheduleDB",
            sa.Column("doctorid", sa.Integer(), sa.ForeignKey("doctorDB.doctorid"), nullable=False),
            sa.Column("day_of_week", sa.Integer(), nullable=False),
            sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("lunch_start", sa.Time(), nullable=True),
            sa.Column("lunch_end", sa.Time(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("doctorid", "day_of_week"),
        )

    if "vet_scheduleDB" in existing:
        op.drop_table("vet_scheduleDB")


def downgrade() -> None:
    op.create_table(
        "vet_scheduleDB",
        sa.Column("vetscheduleid", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doctorid", sa.Integer(), sa.ForeignKey("doctorDB.doctorid"), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("lunch_start", sa.Time(), nullable=True),
        sa.Column("lunch_end", sa.Time(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.drop_table("vet_weekly_scheduleDB")
    op.drop_table("hospital_closed_datesDB")
    op.drop_table("hospital_weekly_scheduleDB")
