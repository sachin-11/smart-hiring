"""resume parsing fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A candidate row now exists from the moment a resume is uploaded, before
    # parsing has run, so these can no longer be NOT NULL.
    op.alter_column("candidates", "full_name", existing_type=sa.String(255), nullable=True)
    op.alter_column("candidates", "email", existing_type=sa.String(255), nullable=True)

    op.add_column("candidates", sa.Column("original_filename", sa.String(255), nullable=True))
    op.add_column("candidates", sa.Column("s3_key", sa.String(1024), nullable=True))
    op.add_column("candidates", sa.Column("experience", sa.JSON(), nullable=True))
    op.add_column("candidates", sa.Column("education", sa.JSON(), nullable=True))
    op.add_column(
        "candidates",
        sa.Column(
            "parsing_status",
            sa.Enum("pending", "processing", "completed", "failed", name="parsing_status"),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("candidates", sa.Column("parsing_error", sa.Text(), nullable=True))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidates_resume_embedding_ivfflat "
        "ON candidates USING ivfflat (resume_embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidates_resume_embedding_ivfflat")

    op.drop_column("candidates", "parsing_error")
    op.drop_column("candidates", "parsing_status")
    op.drop_column("candidates", "education")
    op.drop_column("candidates", "experience")
    op.drop_column("candidates", "s3_key")
    op.drop_column("candidates", "original_filename")

    op.execute("DROP TYPE IF EXISTS parsing_status")

    op.alter_column("candidates", "email", existing_type=sa.String(255), nullable=False)
    op.alter_column("candidates", "full_name", existing_type=sa.String(255), nullable=False)
