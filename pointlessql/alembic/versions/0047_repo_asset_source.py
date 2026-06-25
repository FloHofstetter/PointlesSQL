"""dashboards + saved_queries gain source + repo_yaml_path columns

Phase 51.3 — repo-canonical assets pattern.  Existing UI-created
rows keep ``source='ui'`` (default); new rows materialised from a
``pointlessql.yaml`` inside a synced workspace_repo carry
``source='repo:<slug>'`` and the matching ``repo_yaml_path`` so
the admin UI can render them as read-only.

Two columns per table:

* ``source`` — discriminator string; defaults to ``'ui'``.
* ``repo_yaml_path`` — absolute path to the originating yaml,
  ``NULL`` for UI-created rows.

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-07 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two columns to dashboards + saved_queries."""
    with op.batch_alter_table("dashboards", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=64),
                nullable=False,
                server_default="ui",
            )
        )
        batch_op.add_column(sa.Column("repo_yaml_path", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_dashboards_source",
            ["source"],
            unique=False,
        )

    with op.batch_alter_table("saved_queries", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=64),
                nullable=False,
                server_default="ui",
            )
        )
        batch_op.add_column(sa.Column("repo_yaml_path", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_saved_queries_source",
            ["source"],
            unique=False,
        )


def downgrade() -> None:
    """Drop the two columns + their indexes."""
    with op.batch_alter_table("saved_queries", schema=None) as batch_op:
        batch_op.drop_index("ix_saved_queries_source")
        batch_op.drop_column("repo_yaml_path")
        batch_op.drop_column("source")
    with op.batch_alter_table("dashboards", schema=None) as batch_op:
        batch_op.drop_index("ix_dashboards_source")
        batch_op.drop_column("repo_yaml_path")
        batch_op.drop_column("source")
