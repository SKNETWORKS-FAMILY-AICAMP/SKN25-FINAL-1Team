"""add image position(focal) columns to hospital_profileDB / doctor_profileDB

Revision ID: hosp_img_positions
Revises: hosp_doctor_is_active
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "hosp_img_positions"
down_revision: Union[str, None] = "hosp_doctor_is_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    # 0001 의 create_all 이 현재 모델 기준으로 테이블을 만들 수 있어 중복 add 방지(멱등).
    bind = op.get_bind()
    if "banner_image_position" not in _columns(bind, "hospital_profileDB"):
        op.add_column("hospital_profileDB", sa.Column("banner_image_position", sa.String(), nullable=True))
    if "profile_image_position" not in _columns(bind, "doctor_profileDB"):
        op.add_column("doctor_profileDB", sa.Column("profile_image_position", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if "profile_image_position" in _columns(bind, "doctor_profileDB"):
        op.drop_column("doctor_profileDB", "profile_image_position")
    if "banner_image_position" in _columns(bind, "hospital_profileDB"):
        op.drop_column("hospital_profileDB", "banner_image_position")
