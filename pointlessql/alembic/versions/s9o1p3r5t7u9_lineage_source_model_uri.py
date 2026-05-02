"""lineage_row_edges source_model_uri

Adds a nullable ``source_model_uri`` column to ``lineage_row_edges``
so a write-time call site (typically batch inference: a model
predicts into a Delta table) can stamp the originating
``models:/cat.sch.model/<version>`` URI on every edge it produces.

Existing rows stay ``NULL`` — pre-21.7 writes were table-to-table
only. The model-detail Lineage DAG joins on this column when
building the downstream "Predictions" half of the bidirectional
graph.

Revision ID: s9o1p3r5t7u9
Revises: r8n0p2q4s6u8
Create Date: 2026-04-30 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s9o1p3r5t7u9"
down_revision: str | None = "r8n0p2q4s6u8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable ``source_model_uri`` column + index."""
    op.add_column(
        "lineage_row_edges",
        sa.Column("source_model_uri", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_lineage_row_edges_source_model_uri",
        "lineage_row_edges",
        ["source_model_uri"],
    )


def downgrade() -> None:
    """Drop the ``source_model_uri`` index + column."""
    op.drop_index("ix_lineage_row_edges_source_model_uri", "lineage_row_edges")
    op.drop_column("lineage_row_edges", "source_model_uri")
