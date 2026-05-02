"""agent_run_operations warnings_json (BUG-grand-08)

Adds a nullable Text column for non-fatal side-effect markers
(``[lineage_emit_failed]``, ``[lineage_edges_partial]``,
``[lineage_rejects_partial]``, ``[lineage_column_partial]``,
``[lineage_value_partial]``).  These were previously appended to
``error_message``, which caused the run-detail Operations tab to
paint successful merges as ``status=error`` whenever soyuz was
unreachable mid-emit.

The fix splits the two concerns: ``error_message`` stays the
single source of truth for "the primitive itself raised";
``warnings_json`` carries best-effort post-commit failures as a
JSON-encoded ``{"markers": [str, ...]}`` blob the UI can paint as
a separate warning badge.

Revision ID: w3s5t7u9v1x3
Revises: v2r4s6t8u0w2
Create Date: 2026-05-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w3s5t7u9v1x3"
down_revision: str | None = "v2r4s6t8u0w2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``warnings_json`` Text column."""
    op.add_column(
        "agent_run_operations",
        sa.Column("warnings_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``warnings_json`` column."""
    op.drop_column("agent_run_operations", "warnings_json")
