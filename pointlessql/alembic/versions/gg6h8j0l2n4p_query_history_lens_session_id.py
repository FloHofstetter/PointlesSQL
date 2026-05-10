"""query_history.lens_session_id FK column (Sprint 65.2)

Adds the optional FK from ``query_history`` to ``lens_sessions`` so a
SQL execution driven by the Lens query tool carries an inline link
back to the owning chat session.  Mirrors the existing
``agent_run_id`` link pattern but for Lens.

Nullable + no server_default — every existing row stays unaffected;
only Lens-driven SQL queries populate the column.

Revision ID: gg6h8j0l2n4p
Revises: ff5g7i9k1m3o
Create Date: 2026-05-10 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "gg6h8j0l2n4p"
down_revision: str | None = "ff5g7i9k1m3o"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the optional lens_session_id FK column.

    Uses ``batch_alter_table`` because SQLite cannot ALTER an existing
    table to add a FK constraint inline; alembic's batch mode falls
    back to the copy-rename-attach pattern there while staying
    inline-ALTER on Postgres.
    """
    with op.batch_alter_table("query_history") as batch:
        batch.add_column(
            sa.Column(
                "lens_session_id",
                sa.Integer(),
                sa.ForeignKey(
                    "lens_sessions.id",
                    name="fk_query_history_lens_session_id",
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Drop the lens_session_id FK column."""
    with op.batch_alter_table("query_history") as batch:
        batch.drop_column("lens_session_id")
