"""ingest_sources table for the Ingest UI.

One row per configured external data source.  Workspace-scoped,
owner-pinned.  Seven connector kinds share one row shape — see
:class:`pointlessql.models.ingest.IngestSource` for the discriminator
column + JSON shape conventions.

``config`` / ``secrets`` / ``table_mappings`` are JSON-encoded TEXT
columns (matching the Phase-8 ``jobs.config`` convention so the
migration is identical across SQLite and Postgres).

The schedule itself lives on the existing ``jobs`` table — Phase 82
reuses the Phase-8 scheduler verbatim.  ``ingest_sources.job_id`` is
an optional FK that links the source to its cron job; null when the
source is paused / unscheduled.

Revision ID: 0092
Revises: 0091
Create Date: 2026-05-16 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092"
down_revision: str | None = "0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``ingest_sources`` + supporting indices."""
    op.create_table(
        "ingest_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "config",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "secrets",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "table_mappings",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_ingest_sources_workspace_name",
        "ingest_sources",
        ["workspace_id", "name"],
        unique=True,
    )
    op.create_index(
        "ix_ingest_sources_workspace_kind",
        "ingest_sources",
        ["workspace_id", "kind"],
    )


def downgrade() -> None:
    """Drop ``ingest_sources`` + indices."""
    op.drop_index("ix_ingest_sources_workspace_kind", table_name="ingest_sources")
    op.drop_index("uq_ingest_sources_workspace_name", table_name="ingest_sources")
    op.drop_table("ingest_sources")
