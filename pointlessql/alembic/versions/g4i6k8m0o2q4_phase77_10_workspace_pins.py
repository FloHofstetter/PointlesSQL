"""phase77.10 — workspace_pinned_entities table.

Workspace landing page (``/workspaces/{slug}``) is the GitHub-org
equivalent for a PointlesSQL workspace: a small admin-curated
gallery of pinned entities + a workspace-scoped activity feed +
the workspace README.

This migration adds the storage backbone for the gallery: a
``workspace_pinned_entities`` row links a workspace to a
polymorphic ``social_target`` (any registered entity kind) with a
``pin_order`` for drag-and-drop reordering.

The pin row is its own primitive (not a row in
``workspace_catalog_pins`` which was the Phase-29 catalog-default
hint) so the two concepts can evolve independently.

Schema:

* ``workspace_pinned_entities(workspace_id, social_target_id,
  pin_order, pinned_by_user_id, pinned_at)`` — composite PK on
  ``(workspace_id, social_target_id)``.
* Index on ``(workspace_id, pin_order)`` for the ordered gallery
  query.

Revision ID: g4i6k8m0o2q4
Revises: f3h5j7l9n1p3
Create Date: 2026-05-15 23:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g4i6k8m0o2q4"
down_revision: str | None = "f3h5j7l9n1p3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the workspace-pinned-entities table + ordering index."""
    op.create_table(
        "workspace_pinned_entities",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pin_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pinned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "pinned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id",
            "social_target_id",
            name="pk_workspace_pinned_entities",
        ),
    )
    op.create_index(
        "ix_workspace_pinned_entities_order",
        "workspace_pinned_entities",
        ["workspace_id", "pin_order"],
    )


def downgrade() -> None:
    """Drop the workspace-pinned-entities table + its index."""
    op.drop_index(
        "ix_workspace_pinned_entities_order",
        table_name="workspace_pinned_entities",
    )
    op.drop_table("workspace_pinned_entities")
