"""widen input port kind column for operational_system

The ``data_product_input_ports.kind`` column was created as
``VARCHAR(16)``, but one of its own allowed values —
``operational_system`` — is 18 characters.  SQLite ignores declared
string lengths, so the overflow went unnoticed; PostgreSQL enforces
them and rejects the insert (``value too long for type character
varying(16)``).  Widen the column to ``VARCHAR(32)`` so every value in
``INPUT_PORT_KINDS`` fits on both dialects.

Revision ID: 6523612b48a4
Revises: 64bf0762645a
Create Date: 2026-06-22 07:44:58.753336
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6523612b48a4"
down_revision: str | None = "64bf0762645a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen ``data_product_input_ports.kind`` to ``VARCHAR(32)``."""
    with op.batch_alter_table("data_product_input_ports") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Restore the original ``VARCHAR(16)`` width."""
    with op.batch_alter_table("data_product_input_ports") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
