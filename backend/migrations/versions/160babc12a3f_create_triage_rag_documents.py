"""create triage rag documents

Revision ID: 160babc12a3f
Revises: 0001_initial_schema
Create Date: 2026-06-05 03:04:42.404449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "160babc12a3f"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "triage_rag_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_file", sa.String(), nullable=False),
        sa.Column("department", sa.String(), nullable=False),
        sa.Column("disease", sa.String(), nullable=True),
        sa.Column("life_cycle", sa.String(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_file"),
    )
    op.create_index(
        "ix_triage_rag_documents_department",
        "triage_rag_documents",
        ["department"],
    )
    op.create_index(
        "ix_triage_rag_documents_disease",
        "triage_rag_documents",
        ["disease"],
    )
    op.create_index(
        "ix_triage_rag_documents_life_cycle",
        "triage_rag_documents",
        ["life_cycle"],
    )
    op.execute(
        "CREATE INDEX ix_triage_rag_documents_embedding_hnsw "
        "ON triage_rag_documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_triage_rag_documents_embedding_hnsw")
    op.drop_index("ix_triage_rag_documents_life_cycle", table_name="triage_rag_documents")
    op.drop_index("ix_triage_rag_documents_disease", table_name="triage_rag_documents")
    op.drop_index("ix_triage_rag_documents_department", table_name="triage_rag_documents")
    op.drop_table("triage_rag_documents")
