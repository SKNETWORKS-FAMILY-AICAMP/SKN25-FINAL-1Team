"""add missing hospital FKs (drift fix)

guardian_hospitalDB.hospitalid / hospital_profileDB.hospitalid /
clinic_signup_requestDB.created_hospitalid 는 모델에 ForeignKey 로 선언돼 있으나
실제 DB 에는 제약이 없다(0001 create_all 로 생성된 뒤 f1 의 hospitalDB 재설계
과정에서 cascade 로 사라진 것으로 추정). 모델↔DB 정합을 위해 누락된 FK 를 추가한다.

Revision ID: t1a2b3c4d5e6
Revises: s1a2b3c4d5e6
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op


revision: str = "t1a2b3c4d5e6"
down_revision: Union[str, None] = "s1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (테이블, 제약명, 컬럼) — 모두 hospitalDB.hospitalid 를 참조
_FKS = [
    ("guardian_hospitalDB", "fk_guardian_hospital_hospitalid", "hospitalid"),
    ("hospital_profileDB", "fk_hospital_profile_hospitalid", "hospitalid"),
    ("clinic_signup_requestDB", "fk_clinic_signup_created_hospitalid", "created_hospitalid"),
]


def upgrade() -> None:
    # 멱등 처리: 동일 이름 제약이 있으면 먼저 제거 후 추가.
    for table, name, column in _FKS:
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS {name}')
        op.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT {name} '
            f'FOREIGN KEY ({column}) REFERENCES "hospitalDB"(hospitalid)'
        )


def downgrade() -> None:
    for table, name, _ in _FKS:
        op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS {name}')
