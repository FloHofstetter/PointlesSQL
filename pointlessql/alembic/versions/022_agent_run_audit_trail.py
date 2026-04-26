"""Sprint 13.8: forced audit trail for agent runs.

Revision ID: 022
Revises: 021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the three forced-audit tables and ``runtime_versions``.

    Three tables back the audit guarantee promised by Sprint 13.8:
    ``agent_run_sources`` stores the verbatim notebook bytes the
    runtime declared at registration time so a post-run edit cannot
    erase the trail; ``agent_run_operations`` records every PQL
    primitive call (``autoload`` / ``merge`` / ``write_table`` /
    ``sql``) with input hash + Delta version pre/post + row count;
    ``agent_run_events`` mirrors the Sprint-55 ``alert_events`` shape
    so CloudEvents lifecycle survives webhook outages.  The
    ``runtime_versions`` column on ``agent_runs`` is JSON-as-text so
    receivers don't need a JSON-typed dialect; the runtime fills the
    Python / pql / deltalake / duckdb versions in at registration so
    a deltalake-1.5-pinned bug stays reproducible from the trail.
    """
    op.create_table(
        "agent_run_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_bytes", sa.Text, nullable=False),
        sa.Column("source_sha", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_run_sources_sha",
        "agent_run_sources",
        ["source_sha"],
    )

    op.create_table(
        "agent_run_operations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("op_name", sa.String(length=32), nullable=False),
        sa.Column("params_json", sa.Text, nullable=False),
        sa.Column("target_table", sa.String(length=255), nullable=True),
        sa.Column("input_sha", sa.String(length=64), nullable=True),
        sa.Column("rows_affected", sa.Integer, nullable=True),
        sa.Column("delta_version_before", sa.BigInteger, nullable=True),
        sa.Column("delta_version_after", sa.BigInteger, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.UniqueConstraint("agent_run_id", "ordinal", name="uq_agent_run_operations_ordinal"),
        sa.CheckConstraint(
            "op_name IN ('autoload','merge','write_table','sql')",
            name="ck_agent_run_operations_op_name",
        ),
    )
    op.create_index(
        "ix_agent_run_operations_run",
        "agent_run_operations",
        ["agent_run_id"],
    )

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.CheckConstraint(
            "outcome IN ('pending','delivered','delivery_failed','no_destination')",
            name="ck_agent_run_events_outcome",
        ),
    )
    op.create_index(
        "ix_agent_run_events_fired",
        "agent_run_events",
        ["agent_run_id", "fired_at"],
    )

    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("runtime_versions", sa.Text, nullable=True))


def downgrade() -> None:
    """Drop the Sprint 13.8 audit-trail surface in reverse order."""
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("runtime_versions")

    op.drop_index("ix_agent_run_events_fired", table_name="agent_run_events")
    op.drop_table("agent_run_events")

    op.drop_index("ix_agent_run_operations_run", table_name="agent_run_operations")
    op.drop_table("agent_run_operations")

    op.drop_index("ix_agent_run_sources_sha", table_name="agent_run_sources")
    op.drop_table("agent_run_sources")
