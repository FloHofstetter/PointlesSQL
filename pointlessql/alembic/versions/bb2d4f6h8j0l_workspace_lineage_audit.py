"""workspace_id on lineage / audit_log / governance / query_history (Phase 28.1b)

Sprint 28.1b — completes the audit-side workspace cascade.  After
this migration every PointlesSQL-owned audit/lineage/governance
table carries a workspace_id FK and the FTS5 audit_search vtable
is workspace-aware end-to-end (28.1a brought it for runs / ops /
tool_calls; this migration backfills the trailing query_history
and audit_log axes).

Tables touched (10):

* ``lineage_row_edges.workspace_id``
* ``lineage_row_rejects.workspace_id``
* ``lineage_column_map.workspace_id``
* ``lineage_value_changes.workspace_id``
* ``query_history.workspace_id``
* ``query_history_tables.workspace_id``
* ``audit_log.workspace_id``
* ``governance_events.workspace_id``
* ``unattributed_writes.workspace_id`` (UNIQUE constraint widened
  from ``(table_fqn, delta_version)`` to
  ``(workspace_id, table_fqn, delta_version)`` so the same commit
  can fan out to multiple workspaces)
* ``anomaly_acks.workspace_id`` (UNIQUE constraint widened from
  ``(metric, bin_iso, bin_kind, group_value, group_kind)`` to
  prefix with ``workspace_id`` so two workspaces can independently
  ack the same metric bin)

Every column adds with ``server_default='1'`` so the existing rows
backfill to the seeded default workspace.

FTS5 surgery: query_history and audit_log triggers (placeholder
``workspace_id_expr = '1'`` in 28.1a) flip to
``IFNULL(NEW.workspace_id, 1)``.  Migration drops + recreates the
audit_search vtable + 15 triggers using the updated trigger specs
in :mod:`pointlessql.services.audit_fts` so the new column shape
is in effect for every subsequent insert.

Revision ID: bb2d4f6h8j0l
Revises: aa1c3e5g7i9k
Create Date: 2026-05-05 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb2d4f6h8j0l"
down_revision: str | None = "aa1c3e5g7i9k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table_name, index_name, [index_cols]) — same shape as 28.1a so the
# loop body is identical.  Tables whose unique constraint also changes
# are handled separately below.
_PLAIN_TABLES_AND_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "lineage_row_edges",
        "ix_lineage_row_edges_workspace_run",
        ["workspace_id", "run_id"],
    ),
    (
        "lineage_row_rejects",
        "ix_lineage_row_rejects_workspace_run",
        ["workspace_id", "run_id"],
    ),
    (
        "lineage_column_map",
        "ix_lineage_column_map_workspace_run",
        ["workspace_id", "run_id"],
    ),
    (
        "lineage_value_changes",
        "ix_lineage_value_changes_workspace_run",
        ["workspace_id", "run_id"],
    ),
    (
        "query_history",
        "ix_query_history_workspace_started",
        ["workspace_id", "started_at"],
    ),
    (
        "query_history_tables",
        "ix_query_history_tables_workspace_full",
        ["workspace_id", "full_name"],
    ),
    (
        "audit_log",
        "ix_audit_log_workspace_created",
        ["workspace_id", "created_at"],
    ),
    (
        "governance_events",
        "ix_governance_events_workspace_fired",
        ["workspace_id", "fired_at"],
    ),
)


def upgrade() -> None:
    """Add workspace_id columns + indexes; widen two unique constraints; rebuild FTS5."""
    bind = op.get_bind()

    # 1. Plain workspace_id additions ---------------------------------------
    for table_name, _index_name, _index_cols in _PLAIN_TABLES_AND_INDEXES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "workspace_id",
                    sa.Integer(),
                    sa.ForeignKey("workspaces.id", name=f"fk_{table_name}_workspace_id"),
                    nullable=False,
                    server_default="1",
                )
            )

    # 2. unattributed_writes: workspace_id + UNIQUE constraint widening -----
    # Drop the old (table_fqn, delta_version) UNIQUE in the same batch as the
    # column add + the new triple-column UNIQUE creation.  Batch mode handles
    # the SQLite copy-and-move that drops the old constraint cleanly.
    with op.batch_alter_table("unattributed_writes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", name="fk_unattributed_writes_workspace_id"),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.drop_constraint("uq_unattributed_writes_table_ver", type_="unique")
        batch_op.create_unique_constraint(
            "uq_unattributed_writes_table_ver",
            ["workspace_id", "table_fqn", "delta_version"],
        )

    # 3. anomaly_acks: workspace_id + UNIQUE constraint widening ------------
    with op.batch_alter_table("anomaly_acks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", name="fk_anomaly_acks_workspace_id"),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.drop_constraint("uq_anomaly_acks_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_anomaly_acks_identity",
            [
                "workspace_id",
                "metric",
                "bin_iso",
                "bin_kind",
                "group_value",
                "group_kind",
            ],
        )

    # 4. Belt-and-braces backfill (server_default already filled rows; this
    #    catches any historic NULLs).
    for table_name, _, _ in _PLAIN_TABLES_AND_INDEXES:
        bind.execute(
            sa.text(f"UPDATE {table_name} SET workspace_id = 1 WHERE workspace_id IS NULL")
        )
    bind.execute(
        sa.text("UPDATE unattributed_writes SET workspace_id = 1 WHERE workspace_id IS NULL")
    )
    bind.execute(sa.text("UPDATE anomaly_acks SET workspace_id = 1 WHERE workspace_id IS NULL"))

    # 5. Compound indexes ---------------------------------------------------
    for table_name, index_name, index_cols in _PLAIN_TABLES_AND_INDEXES:
        op.create_index(index_name, table_name, index_cols)
    op.create_index(
        "ix_unattributed_writes_workspace_table",
        "unattributed_writes",
        ["workspace_id", "table_fqn"],
    )
    op.create_index(
        "ix_anomaly_acks_workspace_acked",
        "anomaly_acks",
        ["workspace_id", "acked_at"],
    )

    # 6. FTS5 vtable rebuild (SQLite only) — flip query_history /
    #    audit_log triggers to read NEW.workspace_id ----------------------
    if bind.dialect.name != "sqlite":
        return

    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log"):
        for kind in ("ai", "ad", "au"):
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_{kind}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS audit_search"))

    from pointlessql.services import audit_fts

    bind.execute(sa.text(audit_fts._VTABLE_SQL))  # pyright: ignore[reportPrivateUsage]
    for spec in audit_fts._TRIGGER_SPECS:  # pyright: ignore[reportPrivateUsage]
        for stmt in audit_fts._trigger_statements(spec):  # pyright: ignore[reportPrivateUsage]
            bind.execute(sa.text(stmt))
    for stmt in audit_fts._INITIAL_POPULATION_SQL:  # pyright: ignore[reportPrivateUsage]
        bind.execute(sa.text(stmt))


def downgrade() -> None:
    """Drop indexes + workspace_id columns; restore old UNIQUE constraints."""
    bind = op.get_bind()

    for table_name, index_name, _ in _PLAIN_TABLES_AND_INDEXES:
        op.drop_index(index_name, table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("workspace_id")

    op.drop_index("ix_unattributed_writes_workspace_table", table_name="unattributed_writes")
    with op.batch_alter_table("unattributed_writes") as batch_op:
        batch_op.drop_constraint("uq_unattributed_writes_table_ver", type_="unique")
        batch_op.create_unique_constraint(
            "uq_unattributed_writes_table_ver",
            ["table_fqn", "delta_version"],
        )
        batch_op.drop_column("workspace_id")

    op.drop_index("ix_anomaly_acks_workspace_acked", table_name="anomaly_acks")
    with op.batch_alter_table("anomaly_acks") as batch_op:
        batch_op.drop_constraint("uq_anomaly_acks_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_anomaly_acks_identity",
            ["metric", "bin_iso", "bin_kind", "group_value", "group_kind"],
        )
        batch_op.drop_column("workspace_id")

    if bind.dialect.name != "sqlite":
        return

    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log"):
        for kind in ("ai", "ad", "au"):
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_{kind}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS audit_search"))
