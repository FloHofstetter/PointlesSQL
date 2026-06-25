"""coedit_bus_messages outbox for multi-worker hub fanout

Adds the ``coedit_bus_messages`` outbox table that lets multiple
uvicorn workers exchange co-edit frames via PG ``LISTEN/NOTIFY``
without a Redis dependency.  PG-only — SQLite installs stay
single-worker and the table is never created there.

Revision ID: 0112
Revises: 0111
Create Date: 2026-05-22 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112"
down_revision: str | None = "0111"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``coedit_bus_messages`` outbox table.

    Table lives on both backends so alembic-check's ORM/migration
    drift gate stays satisfied — but only PostgreSQL installs ever
    populate it.  The :class:`CoeditBus` service refuses to start
    against non-PG dialects (see ``services/notebook/coedit_bus.py``)
    so SQLite installs keep their existing single-worker behaviour.
    """
    op.create_table(
        "coedit_bus_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notebook_uuid", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("source_pid", sa.Integer(), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_coedit_bus_ts", "coedit_bus_messages", ["ts"])
    op.create_index(
        "ix_coedit_bus_notebook_ts",
        "coedit_bus_messages",
        ["notebook_uuid", "ts"],
    )


def downgrade() -> None:
    """Drop ``coedit_bus_messages``."""
    op.drop_index("ix_coedit_bus_notebook_ts", table_name="coedit_bus_messages")
    op.drop_index("ix_coedit_bus_ts", table_name="coedit_bus_messages")
    op.drop_table("coedit_bus_messages")
