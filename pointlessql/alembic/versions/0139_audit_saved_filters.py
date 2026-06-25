"""audit cockpit — saved filters table + per-user index

Adds ``audit_saved_filters`` so admins can name their favourite
filter combos (since-window + action + user-substr + target-substr
+ details-regex) and re-apply them with one click instead of
re-typing every time.

Filters are owner-private by default; a per-row
``is_shared_workspace`` flag lets an owner share the filter with
everyone in the workspace.  ``filters_json`` carries the structured
shape so the table doesn't grow a column per future filter dimension.

Revision ID: 0139
Revises: 0138
Create Date: 2026-05-31 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0139"
down_revision: str | None = "0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create audit_saved_filters + supporting indexes."""
    op.create_table(
        "audit_saved_filters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="fk_audit_saved_filters_owner",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column(
            "is_shared_workspace",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_audit_saved_filters_workspace",
                ondelete="CASCADE",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_audit_saved_filters_owner_name"),
    )
    op.create_index(
        "ix_audit_saved_filters_workspace_shared",
        "audit_saved_filters",
        ["workspace_id", "is_shared_workspace"],
    )


def downgrade() -> None:
    """Drop audit_saved_filters + supporting indexes."""
    op.drop_index(
        "ix_audit_saved_filters_workspace_shared",
        table_name="audit_saved_filters",
    )
    op.drop_table("audit_saved_filters")
