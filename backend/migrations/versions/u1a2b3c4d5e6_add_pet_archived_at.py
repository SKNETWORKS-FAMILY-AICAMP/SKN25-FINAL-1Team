"""add_pet_archived_at (pet 보관/숨김)

petDB 에 archived_at(보관 시각)을 추가한다.
보호자가 반려동물을 '삭제'하면 곧장 지우지 않고 보관함으로 숨긴다(NULL=활성, 값=보관 시각).
사망 등으로 더 보이지 않게 하고 싶어도 상담·예약·EMR·처방·문진 기록은 병원 보관 정책에 따라
유지되어야 하므로, 하드 삭제 대신 보관(숨김)을 기본으로 한다.
영구 삭제는 보관함에서, 연결된 진료 기록이 전혀 없는 경우에만 별도로 수행한다.

Revision ID: u1a2b3c4d5e6
Revises: t1a2b3c4d5e6
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = "u1a2b3c4d5e6"
down_revision: Union[str, None] = "t1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 멱등 처리: 컬럼이 이미 있으면 건너뛴다.
    op.execute(
        'ALTER TABLE "petDB" ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL'
    )
    # 보호자 목록/상세가 archived_at IS NULL 로 필터하므로 부분 인덱스로 활성 펫 조회를 돕는다.
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_pet_active_by_user '
        'ON "petDB" (userid) WHERE archived_at IS NULL'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_pet_active_by_user')
    op.drop_column("petDB", "archived_at")
