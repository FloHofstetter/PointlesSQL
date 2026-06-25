"""API-key ACL + usage aggregation tables

Three new tables, all FK to ``api_keys.id`` with ``ondelete="CASCADE"``:

- ``api_key_catalog_grants`` — per-key allowlist of accessible
  ``(catalog, schema?)`` tuples.  Zero rows = unrestricted
  (back-compat default).  ≥1 row = every catalog/schema referenced
  in the SQL must match at least one grant.
- ``api_key_ip_grants`` — per-key IP allowlist as CIDR ranges.
  Zero rows = unrestricted.  ≥1 row = source IP must match at least
  one CIDR.
- ``api_key_usage_buckets`` — aggregated per-minute usage counts
  for the 30-day dashboard.  UPSERT-friendly composite unique key
  on ``(api_key_id, bucket_minute, source_ip)``.

No data migration: every existing key gets zero rows by default,
so behaviour is unchanged until an admin adds a grant.

Revision ID: 0116
Revises: 0115
Create Date: 2026-05-23 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0116"
down_revision: str | None = "0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the 3 ACL + usage tables."""
    op.create_table(
        "api_key_catalog_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("catalog_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "api_key_id", "catalog_name", "schema_name", name="uq_apikey_catalog_grant"
        ),
    )
    op.create_index(
        "ix_api_key_catalog_grants_api_key_id",
        "api_key_catalog_grants",
        ["api_key_id"],
    )

    op.create_table(
        "api_key_ip_grants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cidr", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("api_key_id", "cidr", name="uq_apikey_ip_grant"),
    )
    op.create_index(
        "ix_api_key_ip_grants_api_key_id",
        "api_key_ip_grants",
        ["api_key_id"],
    )

    op.create_table(
        "api_key_usage_buckets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bucket_minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "api_key_id", "bucket_minute", "source_ip", name="uq_apikey_usage_bucket"
        ),
    )
    op.create_index(
        "ix_api_key_usage_buckets_api_key_id",
        "api_key_usage_buckets",
        ["api_key_id"],
    )
    op.create_index(
        "ix_api_key_usage_buckets_bucket_minute",
        "api_key_usage_buckets",
        ["bucket_minute"],
    )


def downgrade() -> None:
    """Drop the 3 ACL + usage tables."""
    op.drop_index("ix_api_key_usage_buckets_bucket_minute", table_name="api_key_usage_buckets")
    op.drop_index("ix_api_key_usage_buckets_api_key_id", table_name="api_key_usage_buckets")
    op.drop_table("api_key_usage_buckets")
    op.drop_index("ix_api_key_ip_grants_api_key_id", table_name="api_key_ip_grants")
    op.drop_table("api_key_ip_grants")
    op.drop_index("ix_api_key_catalog_grants_api_key_id", table_name="api_key_catalog_grants")
    op.drop_table("api_key_catalog_grants")
