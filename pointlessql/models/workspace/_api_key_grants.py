"""per-key ACLs + usage aggregation.

Three new tables, all FK to ``api_keys.id`` with ``ondelete="CASCADE"``:

- :class:`ApiKeyCatalogGrant` — per-key allowlist of accessible
  ``(catalog, schema?)`` tuples.  Zero rows = unrestricted (back-compat
  default).  ≥1 row = every catalog/schema referenced in the
  statement must match at least one grant.  ``schema_name=NULL``
  matches any schema in that catalog.
- :class:`ApiKeyIpGrant` — per-key IP allowlist as CIDR ranges.
  Zero rows = unrestricted.  ≥1 row = request source IP must match.
- :class:`ApiKeyUsageBucket` — aggregated per-minute usage counts
  for the 30-day dashboard.  Counter buffer in process flushes
  every 30s; retention sweep prunes beyond
  ``usage_retention_days`` (default 30).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class ApiKeyCatalogGrant(Base):
    """Per-key catalog/schema allowlist row.

    Semantics: a key with **zero** rows in this table is unrestricted
    (back-compat behaviour for every pre-Phase-120 key).  With **one or
    more** rows, every catalog/schema reference in the statement must
    match at least one grant.  A grant with ``schema_name=NULL``
    matches every schema inside that catalog.
    """

    __tablename__ = "api_key_catalog_grants"
    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "catalog_name", "schema_name", name="uq_apikey_catalog_grant"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    catalog_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class ApiKeyIpGrant(Base):
    """Per-key IP allowlist row (CIDR).

    Zero rows = unrestricted.  ≥1 row = source IP (via the existing
    ``_client_ip(request)`` helper which honours ``X-Forwarded-For``)
    must match at least one CIDR.  Validation happens in the service
    layer via ``ipaddress.ip_network`` before insert.
    """

    __tablename__ = "api_key_ip_grants"
    __table_args__ = (UniqueConstraint("api_key_id", "cidr", name="uq_apikey_ip_grant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cidr: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class ApiKeyUsageBucket(Base):
    """One ``(api_key, minute, source_ip)`` usage aggregate.

    Every successful Bearer auth is recorded into an in-process
    ``collections.Counter`` keyed on this triple.  The scheduler loop
    flushes the counter every 30s into this table via UPSERT, so a
    high-throughput key adds at most one row per minute per distinct
    source IP — bounded write amplification.

    Retention sweep deletes rows older than
    ``settings.api_key_acl.usage_retention_days`` (default 30).
    """

    __tablename__ = "api_key_usage_buckets"
    __table_args__ = (
        UniqueConstraint("api_key_id", "bucket_minute", "source_ip", name="uq_apikey_usage_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bucket_minute: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
