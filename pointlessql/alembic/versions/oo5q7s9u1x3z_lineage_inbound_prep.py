"""lineage_inbound prep: nullable run/op FKs + producer column + api_keys.lineage_inbound

Phase 40 Sprint 40.0 prep migration.  Three independent schema
deltas bundled into one revision so 40.1 / 40.3 / 40.4 can all
read from a single upgraded baseline:

1. ``lineage_row_edges`` and ``lineage_column_map`` get their
   ``run_id`` and ``op_id`` columns relaxed from NOT NULL to NULL
   so external producers (Kafka-Connect, Airflow, dbt-cloud, peer
   PointlesSQL installs) can land edges without a synthetic local
   AgentRun.  Internal inserts always set both, so existing reads
   are unaffected.
2. The same two tables grow a ``producer VARCHAR(255) NULL`` and
   ``external_event_id VARCHAR(64) NULL`` column.  ``producer``
   carries the OpenLineage ``job.namespace`` of the inbound event;
   NULL means "this PointlesSQL install" (the historical default).
   ``external_event_id`` carries the OL ``run.runId`` for inbound-
   event de-dupe and is NULL for locally-emitted edges.
3. ``api_keys`` gets a new ``lineage_inbound BOOLEAN NOT NULL
   DEFAULT FALSE`` scope.  Sprint 40.1's
   ``POST /api/lineage/openlineage`` route gates on this flag —
   independent of supervisor / auditor so a federation-only key
   can land lineage without seeing run audits.

Revision ID: oo5q7s9u1x3z
Revises: nn4p6r8t0v2y
Create Date: 2026-05-06 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "oo5q7s9u1x3z"
down_revision: str | None = "nn4p6r8t0v2y"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Relax FK nullability + add producer/external_event_id + lineage_inbound scope."""
    with op.batch_alter_table("lineage_row_edges", recreate="auto") as batch:
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=True)
        batch.alter_column("op_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("producer", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("external_event_id", sa.String(length=64), nullable=True))
        batch.create_index(
            "ix_lineage_row_edges_producer", ["producer"], unique=False
        )
        batch.create_index(
            "ix_lineage_row_edges_target_producer",
            ["target_table", "producer"],
            unique=False,
        )

    with op.batch_alter_table("lineage_column_map", recreate="auto") as batch:
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=True)
        batch.alter_column("op_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("producer", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("external_event_id", sa.String(length=64), nullable=True))
        batch.create_index(
            "ix_lineage_column_map_producer", ["producer"], unique=False
        )
        batch.create_index(
            "ix_lineage_column_map_target_producer",
            ["target_table", "producer"],
            unique=False,
        )

    with op.batch_alter_table("api_keys", recreate="auto") as batch:
        batch.add_column(
            sa.Column(
                "lineage_inbound",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    """Restore pre-Phase-40 schema.  Inbound rows must be purged first."""
    bind = op.get_bind()
    inbound_edges = bind.execute(
        sa.text("SELECT COUNT(*) FROM lineage_row_edges WHERE producer IS NOT NULL")
    ).scalar_one()
    inbound_maps = bind.execute(
        sa.text("SELECT COUNT(*) FROM lineage_column_map WHERE producer IS NOT NULL")
    ).scalar_one()
    if inbound_edges or inbound_maps:
        raise RuntimeError(
            "lineage_inbound prep downgrade refuses to run while inbound rows exist "
            f"(edges={inbound_edges}, column_maps={inbound_maps}).  Purge with "
            "DELETE FROM lineage_row_edges WHERE producer IS NOT NULL; "
            "DELETE FROM lineage_column_map WHERE producer IS NOT NULL; "
            "before retrying."
        )

    with op.batch_alter_table("api_keys", recreate="auto") as batch:
        batch.drop_column("lineage_inbound")

    with op.batch_alter_table("lineage_column_map", recreate="auto") as batch:
        batch.drop_index("ix_lineage_column_map_target_producer")
        batch.drop_index("ix_lineage_column_map_producer")
        batch.drop_column("external_event_id")
        batch.drop_column("producer")
        batch.alter_column("op_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table("lineage_row_edges", recreate="auto") as batch:
        batch.drop_index("ix_lineage_row_edges_target_producer")
        batch.drop_index("ix_lineage_row_edges_producer")
        batch.drop_column("external_event_id")
        batch.drop_column("producer")
        batch.alter_column("op_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=False)
