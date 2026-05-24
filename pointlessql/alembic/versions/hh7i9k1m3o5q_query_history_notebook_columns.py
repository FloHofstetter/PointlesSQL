"""query_history.notebook_path + notebook_content_hash columns (Sprint 66.5)

Adds two optional columns so a SQL execution that originated from a
notebook SQL cell carries an inline link back to the source file +
the cell identity (FNV-1a-64 content_hash).

Nullable + no server_default — every existing row stays unaffected;
only notebook-driven SQL queries populate the columns.

Revision ID: hh7i9k1m3o5q
Revises: gg6h8j0l2n4p
Create Date: 2026-05-10 22:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "hh7i9k1m3o5q"
down_revision: str | None = "gg6h8j0l2n4p"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the optional notebook_path + notebook_content_hash columns."""
    with op.batch_alter_table("query_history") as batch:
        batch.add_column(sa.Column("notebook_path", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("notebook_content_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop the two notebook-link columns."""
    with op.batch_alter_table("query_history") as batch:
        batch.drop_column("notebook_content_hash")
        batch.drop_column("notebook_path")
