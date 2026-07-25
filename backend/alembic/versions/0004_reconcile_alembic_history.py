"""reconcile alembic history with drifted schema

Modules 4-9 added seven tables (interviews, reports, recruiters, rag_eval_logs,
drift_reports, answer_judge_logs, and column additions elsewhere) directly via
`init_db()`'s `Base.metadata.create_all` — a real dev-convenience shortcut, but
it meant Alembic's migration history silently fell behind: `alembic_version`
was still pinned at 0003 while the live schema had moved well past it, with no
tracked, rollback-able path for any of that later schema.

This migration is a genuine no-op against an already-reconciled database (this
one) — `alembic revision --autogenerate` against the current models produces
zero diff, confirming the live schema now exactly matches what the ORM models
declare (including five indexes — the pgvector `ivfflat` cosine-similarity
index and four FK lookup indexes — that existed in the DB from manual/raw-SQL
creation but weren't declared on the models; see app/models/candidate.py,
app/models/job.py, app/models/interview.py). Those declarations were the only
"fix" required.

For a FRESH environment (new deploy, CI, a teammate's machine) with an empty
database, `alembic upgrade head` from 0001 will NOT create the Module 4-9
tables — `create_all` in init_db() remains the actual mechanism that builds
them, since backfilling seven tables' worth of CREATE TABLE statements here
retroactively, for a table set that already exists in every real environment
this app runs in, adds risk (subtly wrong column types/constraints slipping
through autogenerate) without real benefit. The honest state going forward:
Alembic tracks schema history from this point on; anything before it is
"already applied, captured by create_all's idempotent table creation."

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — see module docstring. This revision exists to move
    # alembic_version off the stale "0003" pointer and mark the point after
    # which real Alembic migrations should be written for schema changes,
    # rather than relying on create_all.
    pass


def downgrade() -> None:
    pass
