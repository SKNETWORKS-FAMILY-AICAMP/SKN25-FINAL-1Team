"""add onboarding/profile tables: hospital_profile, doctor_profile,
clinic_signup_request, admin_user, guardian_hospital

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-06-15 01:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'i1a2b3c4d5e6'
down_revision: Union[str, None] = 'h1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # 0001 의 create_all 이 현재 모델 기준으로 이미 만들었으면 스킵(신규 DB), 없으면 생성(기존 DB).
    if "hospital_profileDB" not in tables:
        op.create_table(
            "hospital_profileDB",
            sa.Column("hospitalid", sa.Integer(), sa.ForeignKey("hospitalDB.hospitalid"), primary_key=True),
            sa.Column("tagline", sa.String(), nullable=True),
            sa.Column("intro", sa.Text(), nullable=True),
            sa.Column("banner_image_url", sa.Text(), nullable=True),
            sa.Column("features", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "doctor_profileDB" not in tables:
        op.create_table(
            "doctor_profileDB",
            sa.Column("doctorid", sa.Integer(), sa.ForeignKey("doctorDB.doctorid"), primary_key=True),
            sa.Column("specialty", sa.String(), nullable=True),
            sa.Column("education", sa.String(), nullable=True),
            sa.Column("bio", sa.Text(), nullable=True),
            sa.Column("specialty_areas", sa.JSON(), nullable=True),
            sa.Column("profile_image_url", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "clinic_signup_requestDB" not in tables:
        op.create_table(
            "clinic_signup_requestDB",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("hospital_name", sa.String(), nullable=False),
            sa.Column("business_number", sa.String(), nullable=False),
            sa.Column("business_license_url", sa.Text(), nullable=True),
            sa.Column("hospital_phone", sa.String(), nullable=True),
            sa.Column("hospital_address", sa.String(), nullable=True),
            sa.Column("owner_email", sa.String(), nullable=True),
            sa.Column("desired_loginid", sa.String(), nullable=False),
            sa.Column("tagline", sa.String(), nullable=True),
            sa.Column("intro", sa.Text(), nullable=True),
            sa.Column("features", sa.JSON(), nullable=True),
            sa.Column("banner_image_url", sa.Text(), nullable=True),
            sa.Column("hours", sa.JSON(), nullable=True),
            sa.Column("doctors", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="접수"),
            sa.Column("reject_reason", sa.Text(), nullable=True),
            sa.Column("created_hospitalid", sa.Integer(), sa.ForeignKey("hospitalDB.hospitalid"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "admin_userDB" not in tables:
        op.create_table(
            "admin_userDB",
            sa.Column("adminid", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("loginid", sa.String(), nullable=False, unique=True),
            sa.Column("password", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "guardian_hospitalDB" not in tables:
        op.create_table(
            "guardian_hospitalDB",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("userid", sa.Integer(), sa.ForeignKey("userDB.userid"), nullable=False),
            sa.Column("hospitalid", sa.Integer(), sa.ForeignKey("hospitalDB.hospitalid"), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("userid", "hospitalid", name="uq_guardian_hospital"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for name in (
        "guardian_hospitalDB",
        "admin_userDB",
        "clinic_signup_requestDB",
        "doctor_profileDB",
        "hospital_profileDB",
    ):
        if name in tables:
            op.drop_table(name)
