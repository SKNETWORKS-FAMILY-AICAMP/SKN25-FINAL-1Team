"""add hospitalid FK to doctorDB

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0001의 create_all이 현재 모델 기준으로 hospitalid 컬럼을 이미 만들었을 수 있으므로
    # 가드 필수 (이 레포 규칙 — d4e5f6a7b8c9 패턴 참고)
    # f1 마이그레이션이 hospitalDB를 DROP CASCADE로 재생성하면 FK 제약이 사라지므로
    # 컬럼은 있지만 FK가 없는 경우도 함께 처리한다.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("doctorDB")}
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("doctorDB")}

    if "hospitalid" not in existing_columns:
        op.add_column(
            "doctorDB",
            sa.Column("hospitalid", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_doctor_hospitalid",
            "doctorDB", "hospitalDB",
            ["hospitalid"], ["hospitalid"],
        )
    elif "fk_doctor_hospitalid" not in existing_fks:
        # 컬럼은 있지만 FK가 CASCADE로 삭제된 경우 복구
        op.create_foreign_key(
            "fk_doctor_hospitalid",
            "doctorDB", "hospitalDB",
            ["hospitalid"], ["hospitalid"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        col["name"]
        for col in sa.inspect(bind).get_columns("doctorDB")
    }

    if "hospitalid" in existing_columns:
        op.drop_constraint("fk_doctor_hospitalid", "doctorDB", type_="foreignkey")
        op.drop_column("doctorDB", "hospitalid")
