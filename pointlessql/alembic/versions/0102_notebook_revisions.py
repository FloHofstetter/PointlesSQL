"""notebook revisions

Adds the ``notebook_revisions`` table that backs the Phase-97 save-
snapshot history.  Each row freezes the (cells + outputs) state at a
discrete save event so the editor's revision-history panel can render
a Monaco diff between any two snapshots and a future replay surface
(Phase 103) can re-execute an old revision against today's data.

Snapshots live in this metadata DB rather than on the on-disk
``.py`` so the file stays IDE-agnostic; outputs travel with the
snapshot so re-rendering an old revision needs no kernel re-run.

The ``content_sha256`` column captures a deterministic hash of the
canonical JSON encoding of ``(cells, outputs)`` and is the basis for
a future shoreguard-fresh cryptographic signature.  ``signature_alg``
and ``signature`` ride along as nullable columns ready for the
shoreguard integration — every snapshot still records its hash, only
the signature step is pending.

Revision ID: 0102
Revises: 0101
Create Date: 2026-05-20 00:42:04.194237
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notebook_revisions`` table."""
    op.create_table(
        "notebook_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_uuid", sa.String(length=36), nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("parent_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("cells_json", sa.Text(), nullable=False),
        sa.Column("outputs_json", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_alg", sa.String(length=32), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["notebook_revisions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notebook_id", "content_sha256", name="uq_notebook_revisions_notebook_sha"
        ),
        sa.UniqueConstraint("revision_uuid"),
    )
    with op.batch_alter_table("notebook_revisions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notebook_revisions_notebook_created",
            ["notebook_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_notebook_revisions_uuid",
            ["revision_uuid"],
            unique=False,
        )


def downgrade() -> None:
    """Drop the ``notebook_revisions`` table."""
    with op.batch_alter_table("notebook_revisions", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_revisions_uuid")
        batch_op.drop_index("ix_notebook_revisions_notebook_created")

    op.drop_table("notebook_revisions")
