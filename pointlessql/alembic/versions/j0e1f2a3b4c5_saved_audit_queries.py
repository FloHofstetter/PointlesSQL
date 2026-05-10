"""saved_audit_queries table + 5 starter rows

 (Audit Cockpit) adds a separate "saved query" surface
scoped to the audit tables.  See
``pointlessql/models/saved_audit_queries.py`` for the column
contract; this migration creates the table and seeds the starter
rows the cockpit lists by default.

Starter rows live with ``is_starter=True`` and ``owner_id=NULL``
so they survive any user deletion.  PATCH and DELETE refuse on
those rows at the service layer (no DB-level enforcement — the
column is the source of truth).

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-04-28 18:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "j0e1f2a3b4c5"
down_revision: str | None = "i9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _date_minus(days: int, dialect_name: str) -> str:
    """Return a dialect-correct "now minus N days" SQL fragment.

    SQLite ships ``datetime('now', '-N days')``; Postgres needs
    ``NOW() - INTERVAL 'N days'``.  Sprint 32.1 — bug surfaced once
    Phase 31 made the PG suite runnable end-to-end; the four
    starter rows below ship as raw SQL strings that the runtime
    executes via ``text()`` without dialect translation.
    """
    if dialect_name == "postgresql":
        return f"NOW() - INTERVAL '{days} days'"
    return f"datetime('now', '-{days} days')"


def starter_rows(dialect_name: str) -> list[dict[str, object]]:
    """Build the 5 starter rows with dialect-correct date arithmetic."""
    d90 = _date_minus(90, dialect_name)
    d30 = _date_minus(30, dialect_name)
    d7 = _date_minus(7, dialect_name)
    return [
        {
            "slug": "pii-writes-last-90d",
            "title": "PII writes — last 90 days",
            "description": (
                "Every `lineage_value_changes` row whose `target_column` "
                "contains the substring `pii` over the last 90 days.\n\n"
                "**When to use:**\n\n"
                "- GDPR Art. 30 evidence — show every PII mutation in a "
                "compliance window.\n"
                "- Investigate after a data-protection incident; pivot "
                "into the row-trace UI from any returned `run_id`.\n"
            ),
            "sql_text": (
                "SELECT vc.run_id, vc.op_id, vc.target_table, vc.target_column,"
                " vc.target_row_id, vc.old_value, vc.new_value, vc.created_at\n"
                "FROM lineage_value_changes vc\n"
                "WHERE LOWER(vc.target_column) LIKE '%pii%'\n"
                f"  AND vc.created_at >= {d90}\n"
                "ORDER BY vc.created_at DESC\n"
                "LIMIT 1000"
            ),
        },
        {
            "slug": "rollbacks-last-quarter",
            "title": "Rollbacks — last 90 days",
            "description": (
                "Every `pql.rollback` operation in the last quarter, "
                "with the principal who triggered it and the Delta "
                "version range.\n\n"
                "Patterns of repeated rollbacks against the same "
                "`target_table` are a good signal that an upstream "
                "agent prompt is unstable — flag those for the audit "
                "reviewer."
            ),
            "sql_text": (
                "SELECT r.id AS run_id, r.principal, r.agent_id,"
                " o.target_table, o.delta_version_before, o.delta_version_after,"
                " o.started_at\n"
                "FROM agent_run_operations o\n"
                "JOIN agent_runs r ON r.id = o.agent_run_id\n"
                "WHERE o.op_name = 'rollback'\n"
                f"  AND o.started_at >= {d90}\n"
                "ORDER BY o.started_at DESC"
            ),
        },
        {
            "slug": "cost-gate-denials-this-week",
            "title": "Cost-gate denials — this week",
            "description": (
                "Runs the EXPLAIN cost gate **denied** in the last 7 "
                "days. The `cost_gate_trigger` column carries the "
                "engine's verdict as JSON.\n\n"
                "Pair with the `runs/<id>/operations` tab to see which "
                "specific operation hit the gate."
            ),
            "sql_text": (
                "SELECT id, principal, agent_id, notebook_path, status,"
                " cost_gate_trigger, started_at\n"
                "FROM agent_runs\n"
                "WHERE status = 'denied'\n"
                "  AND cost_gate_trigger IS NOT NULL\n"
                f"  AND started_at >= {d7}\n"
                "ORDER BY started_at DESC"
            ),
        },
        {
            "slug": "unacknowledged-external-writes",
            "title": "Unacknowledged external writes",
            "description": (
                "Delta-log commits that **no `agent_run_operations` "
                "row claims** — still waiting for admin triage.\n\n"
                "These should be empty in steady state. Non-empty "
                "rows mean either an out-of-band Spark/notebook "
                "write or a missing audit hook on a new write path."
            ),
            "sql_text": (
                "SELECT id, table_fqn, delta_version, commit_timestamp, detected_at\n"
                "FROM unattributed_writes\n"
                "WHERE acknowledged_at IS NULL\n"
                "ORDER BY detected_at DESC"
            ),
        },
        {
            "slug": "top-mutating-principals-30d",
            "title": "Top mutating principals — last 30 days",
            "description": (
                "Sum of `rows_affected` from `merge` and `write_table` "
                "ops, grouped by `principal`, over the last 30 days. "
                "Top 20.\n\n"
                "Mirrors the same panel in the Grafana dashboard, but "
                "in SQL so you can pivot into specific runs without "
                "leaving the cockpit."
            ),
            "sql_text": (
                "SELECT COALESCE(r.principal, '<unknown>') AS principal,"
                " COALESCE(SUM(o.rows_affected), 0) AS rows_written\n"
                "FROM agent_runs r\n"
                "JOIN agent_run_operations o ON o.agent_run_id = r.id\n"
                "WHERE o.op_name IN ('merge', 'write_table')\n"
                f"  AND r.started_at >= {d30}\n"
                "GROUP BY r.principal\n"
                "ORDER BY rows_written DESC\n"
                "LIMIT 20"
            ),
        },
    ]


def upgrade() -> None:
    op.create_table(
        "saved_audit_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_starter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("alert_threshold_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("saved_audit_queries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_saved_audit_queries_owner_updated",
            ["owner_id", "updated_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_saved_audit_queries_starter",
            ["is_starter"],
            unique=False,
        )
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    rows_in = starter_rows(op.get_bind().dialect.name)
    for r in rows_in:
        row: dict[str, object] = dict(r)
        row.update(
            {
                "owner_id": None,
                "is_shared": True,
                "is_starter": True,
                "alert_threshold_count": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        rows.append(row)
    op.bulk_insert(
        sa.table(
            "saved_audit_queries",
            sa.column("slug", sa.String),
            sa.column("title", sa.String),
            sa.column("description", sa.String),
            sa.column("sql_text", sa.Text),
            sa.column("owner_id", sa.Integer),
            sa.column("is_shared", sa.Boolean),
            sa.column("is_starter", sa.Boolean),
            sa.column("alert_threshold_count", sa.Integer),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        rows,
    )


def downgrade() -> None:
    with op.batch_alter_table("saved_audit_queries", schema=None) as batch_op:
        batch_op.drop_index("ix_saved_audit_queries_starter")
        batch_op.drop_index("ix_saved_audit_queries_owner_updated")
    op.drop_table("saved_audit_queries")
