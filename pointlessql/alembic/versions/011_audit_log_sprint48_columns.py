"""Sprint 48 audit-log hardening: widen detail + add client_ip/actor_role.

Revision ID: 011
Revises: 010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``client_ip`` + ``actor_role`` columns and widen ``detail`` to ``Text``.

    Sprint 48 ports three shoreguard-fresh patterns: forensic
    ``client_ip`` (IPv4 or IPv6, so 45 chars is enough for the full
    ``::ffff:255.255.255.255`` form), ``actor_role`` so the viewer
    can badge admin vs. regular actions at a glance, and a
    ``Text`` ``detail`` column that can hold a JSON-encoded dict
    instead of the old 2000-char string cap. The append-only ORM
    guards in ``services/audit.py`` apply to every future row
    regardless of schema — no DDL involved.
    """
    # SQLite doesn't do real ``ALTER COLUMN``, so we use
    # ``batch_alter_table`` which transparently recreates the
    # table when needed. Postgres takes the direct path.
    with op.batch_alter_table("audit_log") as batch:
        batch.alter_column(
            "detail",
            existing_type=sa.String(length=2000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch.add_column(
            sa.Column(
                "client_ip",
                sa.String(length=45),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "actor_role",
                sa.String(length=20),
                nullable=False,
                server_default="user",
            )
        )


def downgrade() -> None:
    """Drop the Sprint 48 columns and narrow ``detail`` back to 2000 chars."""
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("actor_role")
        batch.drop_column("client_ip")
        batch.alter_column(
            "detail",
            existing_type=sa.Text(),
            type_=sa.String(length=2000),
            existing_nullable=True,
        )
