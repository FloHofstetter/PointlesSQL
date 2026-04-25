"""Sprint 13.9: link query_history rows to agent runs.

Revision ID: 023
Revises: 022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable ``agent_run_id`` to ``query_history`` plus a partial index.

    Sprint 13.9 closes the run-to-query gap surfaced during the
    Drift-Monitor demo: an agent's ``pql.sql`` calls (and any
    ad-hoc ``POST /api/sql/execute`` from a Hermes plugin) now
    carry the owning ``agent_run_id`` so the run-detail view can
    answer "which queries did this run execute?" without guessing.

    No FK constraint by design — ``agent_runs.id`` is a
    String(36) UUID; we want query history to outlive a deleted
    run.  The partial index keeps the catalog small for the
    common case where the column is NULL (interactive editor
    queries from human users).
    """
    op.add_column(
        "query_history",
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_query_history_agent_run_id",
        "query_history",
        ["agent_run_id"],
        sqlite_where=sa.text("agent_run_id IS NOT NULL"),
        postgresql_where=sa.text("agent_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the Sprint 13.9 link column."""
    op.drop_index(
        "ix_query_history_agent_run_id",
        table_name="query_history",
    )
    op.drop_column("query_history", "agent_run_id")
