"""Sprint 54: query_history.chart_config.

Revision ID: 014
Revises: 013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable JSON-as-text ``chart_config`` column.

    The editor persists the user's chosen chart type + X/Y column
    selection here so re-running a query from ``/queries`` replays
    the same visualisation.  ``NULL`` (the default) means "show the
    table view", which is correct for every pre-Sprint-54 row.
    """
    op.add_column(
        "query_history",
        sa.Column("chart_config", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Drop the chart-config column."""
    op.drop_column("query_history", "chart_config")
