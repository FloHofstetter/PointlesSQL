"""Sprint 13.5.3: ``autoload_checkpoints`` table.

Revision ID: 021
Revises: 020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``autoload_checkpoints`` table.

    Phase 13.5's autoload primitive (``pql.autoload``) needs a
    durable record of which Volume files it has already pulled
    into a target Delta table so re-running the same autoload
    over a directory is a no-op for previously-ingested files.
    The MVP shape is intentionally narrow: file-level
    exactly-once via SHA-256 of the file bytes, scoped per
    target so the same source file fan-ed into multiple bronze
    tables stays addressable.

    The unique constraint on ``(target_table, file_sha)``
    backs the cheap "have I done this?" lookup; the index on
    ``(target_table, source_path)`` covers the secondary
    listing the run-detail view (a future sprint) will use.
    """
    op.create_table(
        "autoload_checkpoints",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("file_sha", sa.String(length=64), nullable=False),
        sa.Column("target_table", sa.String(length=512), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("rows_ingested", sa.Integer, nullable=False),
        sa.UniqueConstraint("target_table", "file_sha", name="uq_autoload_target_sha"),
    )
    op.create_index(
        "ix_autoload_checkpoints_target_path",
        "autoload_checkpoints",
        ["target_table", "source_path"],
    )


def downgrade() -> None:
    """Drop the Sprint 13.5.3 autoload checkpoints surface."""
    op.drop_index(
        "ix_autoload_checkpoints_target_path",
        table_name="autoload_checkpoints",
    )
    op.drop_table("autoload_checkpoints")
