"""Create dashboards table for Sprint 28.

Revision ID: 008
Revises: 007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Sprint 28 ``dashboards`` table.

    ``job_id`` is nullable and uses ``ON DELETE SET NULL`` so a bound
    job can be deleted without cascading into the dashboard — the
    dashboard survives as an orphan pointing at its notebook_path, and
    the detail page falls back to the empty-state UI until a new job
    is bound. ``slug`` is the URL-visible identifier; ``title`` is
    shown to humans.
    """
    op.create_table(
        "dashboards",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("notebook_path", sa.String(1000), nullable=False),
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop the ``dashboards`` table."""
    op.drop_table("dashboards")
