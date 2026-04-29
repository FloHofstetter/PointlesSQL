"""system_keys table + pii_mode default = hash_only (Sprint 20.1)

Sprint 20.1 ships the PII detection + masking write-hook.  It needs
two pieces of persistent state:

* ``system_keys`` — single row per install-scoped secret.  The PII
  redactor lazily generates a 32-byte URL-safe token under
  ``name='pii_hash'`` at first use when the operator hasn't supplied
  ``POINTLESSQL_AUDIT_PII_HASH_SECRET`` explicitly.
* No schema change to ``lineage_value_changes`` — the redaction
  happens at write time inside ``record_value_changes``.  Existing
  rows stay readable; new writes flow through the hash/redact path
  per ``settings.audit.pii_mode``.

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-04-29 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n4i5j6k7l8m9"
down_revision: str | None = "m3h4i5j6k7l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_system_keys_name"),
    )


def downgrade() -> None:
    op.drop_table("system_keys")
