"""redesign hospitalDB: remove doctorid/scheduleid FK, add business_number

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # hospitalDB는 데이터 없이 잘못된 구조로 방치된 상태.
    # DROP 후 재생성이 ALTER 여러 번보다 안전하고 깔끔하다.
    # loginid/password/is_initial_password를 최종 스키마 기준으로 함께 생성해
    # 이후 g2/h1 마이그레이션이 가드로 안전하게 스킵할 수 있게 한다.
    op.execute('DROP TABLE IF EXISTS "hospitalDB" CASCADE')
    op.execute("""
        CREATE TABLE "hospitalDB" (
            hospitalid          SERIAL PRIMARY KEY,
            hospital_name       VARCHAR NOT NULL,
            hospital_address    VARCHAR,
            hospital_number     VARCHAR,
            business_number     VARCHAR NOT NULL UNIQUE,
            loginid             VARCHAR NOT NULL UNIQUE DEFAULT '',
            password            VARCHAR NOT NULL DEFAULT '',
            is_initial_password BOOLEAN NOT NULL DEFAULT true,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "hospitalDB" CASCADE')
    op.execute("""
        CREATE TABLE "hospitalDB" (
            hospitalid       SERIAL PRIMARY KEY,
            doctorid         INTEGER NOT NULL REFERENCES "doctorDB"(doctorid),
            scheduleid       INTEGER NOT NULL REFERENCES "scheduleDB"(scheduleid),
            hospital_name    VARCHAR NOT NULL,
            hospital_address VARCHAR NOT NULL,
            hospital_number  VARCHAR NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ
        )
    """)
