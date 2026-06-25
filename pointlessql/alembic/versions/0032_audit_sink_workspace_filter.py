"""audit_sinks.workspace_filter for per-workspace routing

Adds a nullable JSON-text column ``workspace_filter`` to ``audit_sinks``.
``NULL`` (the default) keeps install-global fan-out semantics — every
workspace's governance events fire every active sink, matching the
pre-29.1 behaviour.  A non-null list like ``[1, 3]`` restricts the
sink to events whose ``workspace_id`` is one of the listed values.

The dispatcher predicate is implemented in
:func:`pointlessql.services.audit.sinks._select_active_sinks`; see
also :func:`pointlessql.services.workspace.governance.emit_governance_event`
for the call site that threads ``workspace_id`` through.

No backfill is required because ``NULL`` already means "all
workspaces".

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``audit_sinks.workspace_filter`` (nullable JSON-text column)."""
    op.add_column(
        "audit_sinks",
        sa.Column("workspace_filter", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop ``audit_sinks.workspace_filter``."""
    op.drop_column("audit_sinks", "workspace_filter")
