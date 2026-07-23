"""jd analysis fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("nice_to_have_skills", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column("jobs", sa.Column("responsibilities", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "seniority_level",
            sa.Enum("junior", "mid", "senior", "lead", "principal", name="seniority_level"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "seniority_level")
    op.drop_column("jobs", "responsibilities")
    op.drop_column("jobs", "nice_to_have_skills")

    op.execute("DROP TYPE IF EXISTS seniority_level")
