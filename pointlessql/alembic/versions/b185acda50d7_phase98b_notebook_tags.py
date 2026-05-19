"""phase98b — notebook tags + template-gallery

Adds the ``notebook_tags`` table that backs the Phase-98.B notebook-
level tag picker.  Notebook tags categorise a whole notebook in the
workspace tree (``etl`` / ``draft`` / ``prod`` / etc.).  They are
distinct from the Phase-95.3 *cell* tags which ride the marker
grammar — those tag a single cell inside the on-disk ``.py``, this
table tags the notebook entity.

The template-gallery side of Phase 98.B is filesystem-only; it
ships starter ``.py`` files under
``pointlessql/data/notebook_templates/`` and needs no schema change.

Revision ID: b185acda50d7
Revises: u9w1y3a5d7f9
Create Date: 2026-05-20 00:22:23.783223
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b185acda50d7"
down_revision: str | None = "u9w1y3a5d7f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notebook_tags`` table."""
    op.create_table(
        "notebook_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"], ["notebooks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notebook_id", "tag", name="uq_notebook_tags_notebook_tag"
        ),
    )
    with op.batch_alter_table("notebook_tags", schema=None) as batch_op:
        batch_op.create_index("ix_notebook_tags_tag", ["tag"], unique=False)


def downgrade() -> None:
    """Drop the ``notebook_tags`` table."""
    with op.batch_alter_table("notebook_tags", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_tags_tag")

    op.drop_table("notebook_tags")
