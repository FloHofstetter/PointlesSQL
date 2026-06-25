"""notebook widgets + permissions

Adds two tables that back the Phase-99 widget-cells +
notebook-permissions surface:

* ``notebook_widgets`` — parameter widgets (dropdown / slider / text)
  defined per notebook.  The kernel-side ``pql.widgets`` shim reads
  the current values via env bridge so a parameterised notebook
  drives execution from a form rather than hard-coded constants.
* ``notebook_permissions`` — per-notebook share roles (view / run /
  edit) layered on top of workspace membership.  A row here grants
  access *in addition* to the workspace default permissioning so a
  notebook can be shared without granting workspace-wide edit.

Revision ID: 0104
Revises: 0103
Create Date: 2026-05-20 06:09:18.650675
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0104"
down_revision: str | None = "0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_permissions`` + ``notebook_widgets``."""
    op.create_table(
        "notebook_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notebook_id", "user_id", name="uq_notebook_perms_per_user"),
    )
    with op.batch_alter_table("notebook_permissions", schema=None) as batch_op:
        batch_op.create_index("ix_notebook_perms_user", ["user_id"], unique=False)

    op.create_table(
        "notebook_widgets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("widget_kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notebook_id", "name", name="uq_notebook_widgets_name_per_nb"),
    )
    with op.batch_alter_table("notebook_widgets", schema=None) as batch_op:
        batch_op.create_index("ix_notebook_widgets_notebook", ["notebook_id"], unique=False)


def downgrade() -> None:
    """Drop both Phase-99 tables."""
    with op.batch_alter_table("notebook_widgets", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_widgets_notebook")
    op.drop_table("notebook_widgets")
    with op.batch_alter_table("notebook_permissions", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_perms_user")
    op.drop_table("notebook_permissions")
