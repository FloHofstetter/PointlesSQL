"""phase 189: actionable_signals open-ledger for data-health cards

Adds ``actionable_signals`` — one row per ongoing data-health /
pipeline problem (alert firing, SLO breach, contract violation,
freshness stale, job/ingest failure).  The feed live-unions every
``status='open'`` row so a card reflects current state and drops when
the problem clears.

A partial unique index on ``dedupe_key`` while ``status='open'`` is
the storm guard: a check that re-fires every scheduler tick bumps
``last_seen_at`` instead of stacking duplicate cards.  Resolved rows
are exempt so the same problem can recur and keep its history.

Revision ID: p4d6f8h0j2l4
Revises: o3c5e7g9i1k3
Create Date: 2026-06-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p4d6f8h0j2l4"
down_revision: str | None = "o3c5e7g9i1k3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create actionable_signals + the partial-open unique index."""
    op.create_table(
        "actionable_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_actionable_signals_workspace",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("signal_kind", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("entity_kind", sa.String(32), nullable=False),
        sa.Column("entity_ref", sa.String(500), nullable=False),
        sa.Column("dedupe_key", sa.String(600), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_actionable_signals_open",
        "actionable_signals",
        ["dedupe_key"],
        unique=True,
        sqlite_where=sa.text("status = 'open'"),
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_actionable_signals_ws_status",
        "actionable_signals",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop actionable_signals + its indexes."""
    op.drop_index("ix_actionable_signals_ws_status", table_name="actionable_signals")
    op.drop_index("uq_actionable_signals_open", table_name="actionable_signals")
    op.drop_table("actionable_signals")
