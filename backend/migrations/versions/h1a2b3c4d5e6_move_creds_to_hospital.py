"""move loginid/password/is_initial_password to hospitalDB, strip from doctorDB

Revision ID: h1a2b3c4d5e6
Revises: g2b3c4d5e6f7
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'h1a2b3c4d5e6'
down_revision: Union[str, None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    hospital_cols = {col["name"] for col in inspector.get_columns("hospitalDB")}
    doctor_cols   = {col["name"] for col in inspector.get_columns("doctorDB")}

    # ── 1. hospitalDB에 인증 컬럼 추가 (0001 create_all이 이미 만들었으면 스킵) ──
    if "loginid" not in hospital_cols:
        op.add_column("hospitalDB", sa.Column("loginid", sa.String(), nullable=True))
        op.add_column("hospitalDB", sa.Column("password", sa.String(), nullable=True))
        op.add_column("hospitalDB", sa.Column(
            "is_initial_password", sa.Boolean(), nullable=True,
            server_default=sa.text("true")
        ))

        # 기존 DB(구 스키마)에서만 데이터 이전: doctorDB에 loginid가 있을 때만 실행
        # 신규 DB(./dev.sh reset)는 doctorDB에 loginid 컬럼 자체가 없으므로 스킵
        if "loginid" in doctor_cols:
            bind.execute(sa.text("""
                UPDATE "hospitalDB" h
                SET loginid             = d.loginid,
                    password            = d.password,
                    is_initial_password = d.is_initial_password
                FROM "doctorDB" d
                WHERE d.hospitalid = h.hospitalid
                  AND d.loginid IS NOT NULL
                  AND h.loginid IS NULL
            """))

        op.alter_column("hospitalDB", "loginid",             nullable=False)
        op.alter_column("hospitalDB", "password",            nullable=False)
        op.alter_column("hospitalDB", "is_initial_password", nullable=False)
        op.create_unique_constraint("uq_hospitalDB_loginid", "hospitalDB", ["loginid"])

    # ── 2. doctorDB에서 병원 인증 컬럼 제거 (이미 없으면 스킵) ──
    if "loginid" in doctor_cols:
        op.drop_constraint("doctorDB_loginid_key",          "doctorDB", type_="unique")
        op.drop_column("doctorDB", "loginid")

    if "password" in doctor_cols:
        op.drop_column("doctorDB", "password")

    if "is_initial_password" in doctor_cols:
        op.drop_column("doctorDB", "is_initial_password")

    if "hospital_name" in doctor_cols:
        op.drop_column("doctorDB", "hospital_name")

    if "hospital_address" in doctor_cols:
        op.drop_column("doctorDB", "hospital_address")

    if "hospital_number" in doctor_cols:
        op.drop_column("doctorDB", "hospital_number")

    if "business_number" in doctor_cols:
        op.drop_constraint("doctorDB_business_number_key", "doctorDB", type_="unique")
        op.drop_column("doctorDB", "business_number")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    doctor_cols   = {col["name"] for col in inspector.get_columns("doctorDB")}
    hospital_cols = {col["name"] for col in inspector.get_columns("hospitalDB")}

    # doctorDB에 컬럼 복원
    if "loginid" not in doctor_cols:
        op.add_column("doctorDB", sa.Column("loginid",             sa.String(), nullable=True))
        op.add_column("doctorDB", sa.Column("password",            sa.String(), nullable=True))
        op.add_column("doctorDB", sa.Column("is_initial_password", sa.Boolean(), nullable=True))
        op.add_column("doctorDB", sa.Column("hospital_name",    sa.String(), nullable=True))
        op.add_column("doctorDB", sa.Column("hospital_address", sa.String(), nullable=True))
        op.add_column("doctorDB", sa.Column("hospital_number",  sa.String(), nullable=True))
        op.add_column("doctorDB", sa.Column("business_number",  sa.String(), nullable=True))

    # hospitalDB에서 인증 컬럼 제거
    if "loginid" in hospital_cols:
        op.drop_constraint("uq_hospitalDB_loginid", "hospitalDB", type_="unique")
        op.drop_column("hospitalDB", "loginid")
        op.drop_column("hospitalDB", "password")
        op.drop_column("hospitalDB", "is_initial_password")
