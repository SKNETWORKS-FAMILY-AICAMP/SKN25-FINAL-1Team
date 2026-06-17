"""add original_image, doodle_strokes to petDB (사진 꾸미기 비파괴 편집)

Revision ID: o1a2b3c4d5e6
Revises: n1a2b3c4d5e6
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "o1a2b3c4d5e6"
down_revision: Union[str, None] = "n1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("petDB")}

    # 신규 DB는 create_all 이 모델 기준으로 이미 만들었을 수 있으므로 존재 시 스킵.
    if "original_image" not in columns:
        op.add_column("petDB", sa.Column("original_image", sa.String(), nullable=True))
    if "doodle_strokes" not in columns:
        op.add_column("petDB", sa.Column("doodle_strokes", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("petDB")}

    if "doodle_strokes" in columns:
        op.drop_column("petDB", "doodle_strokes")
    if "original_image" in columns:
        op.drop_column("petDB", "original_image")
