"""phase77 — social_targets polymorphic anchor + DP backfill

Introduces the polymorphic ``social_targets`` anchor table that
Phase 77 keys every social row on.  This is the foundation
migration; subsequent Phase-77.0 migrations add
``social_target_id`` columns to the seven existing social
tables and (in a later revision) drop the now-redundant
``data_product_id`` columns.

Schema strategy = sidecar polymorphic anchor (locked decision
#1 in the Phase 77 plan):  comments / reviews / endorsements /
follows / reactions / readmes will point at ``social_targets.id``
instead of ``data_products.id`` directly.  CASCADE-on-DP-delete
is preserved via the optional ``data_product_id`` back-pointer
on ``social_targets`` for ``entity_kind='dp'`` rows only — the
column is NULL for every other kind so foreign UC entities
(tables / models / branches that don't live in the PointlesSQL
DB at all) can hang a target without inventing a fake DP row.

Backfill creates one ``social_targets`` row per existing
``data_products`` row in the same migration so the next-revision
backfill of ``social_target_id`` columns has a foreign key to
point at.

Revision ID: v3y5a7c9e1g3
Revises: u2w4y6a8c0e3
Create Date: 2026-05-13 23:59:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v3y5a7c9e1g3"
down_revision: str | None = "u2w4y6a8c0e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``social_targets`` and backfill one row per DP."""
    op.create_table(
        "social_targets",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("entity_kind", sa.String(32), nullable=False),
        sa.Column("entity_ref", sa.String(500), nullable=False),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "entity_kind",
            "entity_ref",
            name="uq_social_targets_entity",
        ),
        sa.CheckConstraint(
            "entity_kind IN ("
            "'dp', 'table', 'schema', 'catalog', "
            "'model', 'branch', 'run', 'query', "
            "'notebook', 'saved_query', 'issue', "
            "'workspace'"
            ")",
            name="ck_social_targets_kind",
        ),
        sa.CheckConstraint(
            "(entity_kind = 'dp' AND data_product_id IS NOT NULL) "
            "OR (entity_kind <> 'dp' AND data_product_id IS NULL)",
            name="ck_social_targets_dp_backref",
        ),
    )
    op.create_index(
        "ix_social_targets_kind_ref",
        "social_targets",
        ["entity_kind", "entity_ref"],
    )
    op.create_index(
        "ix_social_targets_dp",
        "social_targets",
        ["data_product_id"],
    )
    # Backfill: one row per existing data product.  ``entity_ref``
    # is the ``catalog.schema`` FQN — same shape ``#dp:`` citation
    # tokens already use, so downstream resolvers stay symmetric.
    op.execute(
        """
        INSERT INTO social_targets (
            workspace_id, entity_kind, entity_ref,
            data_product_id, created_at
        )
        SELECT
            workspace_id,
            'dp',
            catalog_name || '.' || schema_name,
            id,
            created_at
        FROM data_products
        """
    )


def downgrade() -> None:
    """Drop ``social_targets`` and its indexes."""
    op.drop_index("ix_social_targets_dp", table_name="social_targets")
    op.drop_index("ix_social_targets_kind_ref", table_name="social_targets")
    op.drop_table("social_targets")
