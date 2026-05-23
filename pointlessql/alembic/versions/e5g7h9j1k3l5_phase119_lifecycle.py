"""phase 119: api-key lifecycle columns

Seven new ``api_keys`` columns supporting TTL + rotation + soft
quarantine.  All NULL-able with NULL = no constraint (back-compat
default for every existing key — no behaviour change without explicit
admin opt-in):

- ``expires_at`` — TTL deadline; NULL = no expiry.
- ``rotated_from_id`` — FK self-reference to the predecessor key
  during rotation; NULL for natively-created keys.  ``ondelete="SET
  NULL"`` so deleting a predecessor never cascades.
- ``rotated_at`` — set on the *predecessor* when ``rotate`` mints a
  successor; predecessor stays valid through the rotation grace
  window.
- ``grace_until`` — predecessor remains valid until this timestamp
  after rotation.  Configurable, defaults to 24h.
- ``quarantined_at`` — soft-disable timestamp.  Quarantined keys
  return 403 from auth instead of 401 so operators can tell incidents
  apart from typos.
- ``quarantine_reason`` — short admin note (max 200 chars).
- ``expiry_warned_at`` — last time the lifecycle sweep emitted an
  ``api_key.expiry_warning`` audit row; used to dedup so the audit
  log isn't flooded with the same warning every scheduler tick.

Revision ID: e5g7h9j1k3l5
Revises: d3e5f7g9b1c4
Create Date: 2026-05-23 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5g7h9j1k3l5"
down_revision: str | None = "d3e5f7g9b1c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 7 lifecycle columns to ``api_keys``."""
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # rotated_from_id is a self-FK; use batch mode so SQLite can rewrite
    # the table with the new FK constraint cleanly.
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(
            sa.Column("rotated_from_id", sa.Integer(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_api_keys_rotated_from_id",
            "api_keys",
            ["rotated_from_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column(
        "api_keys",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("quarantine_reason", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("expiry_warned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the 7 lifecycle columns."""
    op.drop_column("api_keys", "expiry_warned_at")
    op.drop_column("api_keys", "quarantine_reason")
    op.drop_column("api_keys", "quarantined_at")
    op.drop_column("api_keys", "grace_until")
    op.drop_column("api_keys", "rotated_at")
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_constraint("fk_api_keys_rotated_from_id", type_="foreignkey")
        batch_op.drop_column("rotated_from_id")
    op.drop_column("api_keys", "expires_at")
