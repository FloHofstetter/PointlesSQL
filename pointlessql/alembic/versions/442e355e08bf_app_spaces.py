"""app_spaces

Adds App Spaces — a governance boundary grouping several hosted apps and
declaring their shared API scopes once.  Creates the ``app_spaces``
registry table and a nullable ``hosted_apps.app_space_id`` FK (SET NULL
on space delete so an app survives losing its space).

Revision ID: 442e355e08bf
Revises: aef5cb590bd7
Create Date: 2026-06-21 00:16:06.777431
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "442e355e08bf"
down_revision: str | None = "aef5cb590bd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``app_spaces`` and the ``hosted_apps.app_space_id`` FK."""
    op.create_table(
        "app_spaces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("api_scopes", sa.Text(), server_default="[]", nullable=False),
        sa.Column("created_by", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_app_spaces_ws_name"),
    )
    with op.batch_alter_table("hosted_apps", schema=None) as batch_op:
        batch_op.add_column(sa.Column("app_space_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_hosted_apps_app_space",
            "app_spaces",
            ["app_space_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop the ``app_space_id`` FK + column and the ``app_spaces`` table."""
    with op.batch_alter_table("hosted_apps", schema=None) as batch_op:
        batch_op.drop_constraint("fk_hosted_apps_app_space", type_="foreignkey")
        batch_op.drop_column("app_space_id")
    op.drop_table("app_spaces")
