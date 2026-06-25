"""mcp service registry

Creates the two tables behind the governed MCP service registry: the
workspace inventory of approved external Model Context Protocol
services (``mcp_services``) and the per-service advertised-tool list
with its per-tool allow toggle (``mcp_service_tools``).  Both live in
PointlesSQL's own metadata DB — they govern which external tool
surfaces a workspace has vetted, not lakehouse metadata.

Revision ID: 0160
Revises: 0159
Create Date: 2026-06-20 20:03:23.592485
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0160"
down_revision: str | None = "0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_services",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("secret_scope", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transport IN ('sse', 'http', 'stdio')", name="ck_mcp_services_transport"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_mcp_services_ws_name"),
    )
    with op.batch_alter_table("mcp_services", schema=None) as batch_op:
        batch_op.create_index("ix_mcp_services_workspace", ["workspace_id"], unique=False)

    op.create_table(
        "mcp_service_tools",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["mcp_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "name", name="uq_mcp_service_tools_service_name"),
    )
    with op.batch_alter_table("mcp_service_tools", schema=None) as batch_op:
        batch_op.create_index("ix_mcp_service_tools_service", ["service_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mcp_service_tools", schema=None) as batch_op:
        batch_op.drop_index("ix_mcp_service_tools_service")
    op.drop_table("mcp_service_tools")
    with op.batch_alter_table("mcp_services", schema=None) as batch_op:
        batch_op.drop_index("ix_mcp_services_workspace")
    op.drop_table("mcp_services")
