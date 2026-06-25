"""per-output-port identity constraints (E10)

Adds ``identity_requirements`` JSON-Text nullable column to
``data_product_output_ports``.  When set, every consumer that touches
the port (event-stream, export, WS) is checked against the JSON spec
(OIDC audiences, required scopes, min role).

The PQL-layer hook registry (B6) is a code-only addition — no schema
change — so it ships in this migration's docstring scope but not in
the DDL.

Revision ID: 0129
Revises: 0128
Create Date: 2026-05-30 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0129"
down_revision: str | None = "0128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the identity-requirements JSON column."""
    op.add_column(
        "data_product_output_ports",
        sa.Column("identity_requirements", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the identity-requirements JSON column."""
    op.drop_column("data_product_output_ports", "identity_requirements")
