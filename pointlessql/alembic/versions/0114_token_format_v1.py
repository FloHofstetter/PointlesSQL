"""token format v1 columns

Two schema additions + one column widening to support the new
``pql_{env}_v1_{body40}_{crc8}`` token format alongside legacy
``secrets.token_urlsafe(32)`` tokens:

1. ``api_keys.token_format`` VARCHAR(8) NOT NULL DEFAULT 'legacy'
   — values: ``'legacy'`` for pre-118 keys, ``'v1'`` for new format.
2. ``api_keys.token_env`` VARCHAR(8) NOT NULL DEFAULT 'legacy'
   — values: ``'legacy'`` for pre-118 keys, ``'live'`` / ``'test'``
   for new format.
3. ``api_keys.secret_prefix`` widened from VARCHAR(8) → VARCHAR(32)
   so the new keys' visible prefix (``pql_live_v1_xxxxxxxxxx``,
   ~24 chars) fits.  Legacy keys keep their 8-char prefix.

No data backfill needed: every existing key gets
``token_format='legacy'`` / ``token_env='legacy'`` via server_default
and the secret_prefix widening is a no-op for already-populated rows.

Revision ID: 0114
Revises: 0113
Create Date: 2026-05-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0114"
down_revision: str | None = "0113"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add token_format + token_env, widen secret_prefix."""
    op.add_column(
        "api_keys",
        sa.Column(
            "token_format",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column(
            "token_env",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    # Widen secret_prefix; batch_alter_table for SQLite compatibility.
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.alter_column(
            "secret_prefix",
            existing_type=sa.String(length=8),
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Drop new columns + narrow secret_prefix back to VARCHAR(8)."""
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.alter_column(
            "secret_prefix",
            existing_type=sa.String(length=32),
            type_=sa.String(length=8),
            existing_nullable=False,
        )
    op.drop_column("api_keys", "token_env")
    op.drop_column("api_keys", "token_format")
