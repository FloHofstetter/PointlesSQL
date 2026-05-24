"""phase100 — notebook shares

Adds the ``notebook_shares`` table that backs the Phase-100 public-
share + dashboard surface.  Each row mints a v4 UUID so a notebook
can be reached read-only under ``/share/notebook/{share_uuid}``
without authentication.  ``share_mode ∈ {"snapshot", "live"}``
distinguishes a frozen view (pointing at a Phase-97
:class:`NotebookRevision`) from a live one; ``dashboard_mode``
toggles between regular notebook rendering and a code-stripped
markdown+outputs render.

Revision ID: 8c7c6eb5add5
Revises: b944b9be7e03
Create Date: 2026-05-20 06:15:48.055652
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c7c6eb5add5"
down_revision: str | None = "b944b9be7e03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notebook_shares`` table."""
    op.create_table(
        "notebook_shares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("share_uuid", sa.String(length=36), nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("share_mode", sa.String(length=10), nullable=False),
        sa.Column(
            "dashboard_mode",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("revision_uuid", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_uuid", name="uq_notebook_shares_uuid"),
    )
    with op.batch_alter_table("notebook_shares", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notebook_shares_notebook_active",
            ["notebook_id", "revoked_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notebook_shares``."""
    with op.batch_alter_table("notebook_shares", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_shares_notebook_active")
    op.drop_table("notebook_shares")
