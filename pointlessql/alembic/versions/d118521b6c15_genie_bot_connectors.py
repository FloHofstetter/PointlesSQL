"""genie bot connectors

Adds the ``genie_bot_connectors`` registry — one row per outbound chat
bridge (a Microsoft Teams ``@Genie`` bot or an M365 Copilot connector).
Each connector carries a stable ``public_id`` addressing its inbound
messaging endpoint, a SHA-256 token hash for shared-secret auth, an
optional bound Genie space slug, and an enabled flag.

Revision ID: d118521b6c15
Revises: 442e355e08bf
Create Date: 2026-06-21 01:03:33.224002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d118521b6c15"
down_revision: str | None = "442e355e08bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``genie_bot_connectors`` registry table."""
    op.create_table(
        "genie_bot_connectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=16), server_default="teams", nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("genie_space_slug", sa.String(length=200), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_genie_bot_connectors_public_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_genie_bot_connectors_ws_name"),
    )


def downgrade() -> None:
    """Drop the ``genie_bot_connectors`` registry table."""
    op.drop_table("genie_bot_connectors")
