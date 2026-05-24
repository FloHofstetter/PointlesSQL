"""phase105 — notebook crdt state sidecar table

Adds the sidecar persistence layer for Phase-105 real-time co-edit.
One row per notebook holds the current Y.Doc binary update blob plus a
compaction watermark.  The ``.py`` on disk stays IDE-agnostic (per
``feedback_notebook_py_editability``); the CRDT state lives entirely
in metadata so reverting / cloning / exporting the notebook never
collides with the live edit session.

The blob is the output of ``pycrdt.Doc.get_update()`` (full state
encoding).  Loading is a single ``Doc(); doc.apply_update(blob)`` on
the server side; the WS layer (105.2) then proxies sync + awareness
frames between connected clients.

Compaction (105.8) collapses accumulated updates into a fresh
``get_update()`` snapshot once the blob crosses 256 KiB or after 24 h
of edits — the ``compacted_at`` watermark guards the throttle.

Revision ID: e9f2b4c6d8a0
Revises: d8f1a3b5c7e9
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f2b4c6d8a0"
down_revision: str | None = "d8f1a3b5c7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_crdt_state``."""
    op.create_table(
        "notebook_crdt_state",
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("y_doc_blob", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("compacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notebook_id"),
    )


def downgrade() -> None:
    """Drop ``notebook_crdt_state``."""
    op.drop_table("notebook_crdt_state")
