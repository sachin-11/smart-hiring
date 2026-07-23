"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("resume_url", sa.String(1024), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("experience_years", sa.Float(), nullable=True),
        sa.Column("resume_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new", "screening", "interviewing", "offered", "hired", "rejected",
                name="candidate_status",
            ),
            nullable=False,
            server_default="new",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_candidates_email", "candidates", ["email"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column(
            "employment_type",
            sa.Enum(
                "full_time", "part_time", "contract", "internship",
                name="employment_type",
            ),
            nullable=False,
            server_default="full_time",
        ),
        sa.Column("min_experience", sa.Float(), nullable=True),
        sa.Column("max_experience", sa.Float(), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("required_skills", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("description_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "open", "paused", "closed", name="job_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "applied", "shortlisted", "interviewing", "offered", "rejected", "withdrawn",
                name="application_status",
            ),
            nullable=False,
            server_default="applied",
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])

    op.create_table(
        "interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "interview_type",
            sa.Enum("screening", "technical", "behavioral", "final", name="interview_type"),
            nullable=False,
            server_default="screening",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled", "in_progress", "completed", "cancelled", "no_show",
                name="interview_status",
            ),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("recording_url", sa.String(1024), nullable=True),
        sa.Column("ai_score", sa.Float(), nullable=True),
        sa.Column("ai_feedback", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_interviews_candidate_id", "interviews", ["candidate_id"])
    op.create_index("ix_interviews_job_id", "interviews", ["job_id"])


def downgrade() -> None:
    op.drop_table("interviews")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("candidates")

    op.execute("DROP TYPE IF EXISTS interview_status")
    op.execute("DROP TYPE IF EXISTS interview_type")
    op.execute("DROP TYPE IF EXISTS application_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS employment_type")
    op.execute("DROP TYPE IF EXISTS candidate_status")
