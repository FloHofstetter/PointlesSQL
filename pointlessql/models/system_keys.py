"""Persistent system-key storage (Sprint 20.1).

Some PointlesSQL features need long-lived install-scoped secrets
that must survive restarts but should never appear in env vars or
config files (rotation-friendly, no leak via process lists).

The first consumer is the PII hashing secret used by Sprint 20.1's
write-time redaction layer: when ``pii_mode`` is ``hash_only`` and
no operator-supplied ``POINTLESSQL_AUDIT_PII_HASH_SECRET`` is in the
environment, the redactor lazily generates a 32-byte URL-safe random
token at first use and stores it here.  Same install always produces
the same hash for the same cleartext as long as this row is intact.

Future tenants of this table: any other "install-scoped, never
rotated unless the admin explicitly opts" secret — never user
credentials, never tenant-scoped data.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SystemKey(Base):
    """One install-scoped persistent secret.

    Attributes:
        id: Auto-incremented primary key.
        name: Logical name, unique across the install.  By
            convention lowercase snake_case (``pii_hash``,
            ``cdf_signing``, ...).
        value: Opaque secret bytes, base64url-encoded.  No structure
            is enforced — consumers parse as appropriate.
        created_at: First-write timestamp.  Rotation overwrites the
            ``value`` in place; ``created_at`` stays at the original
            row birth so an audit trail shows when the install
            first needed the key.
    """

    __tablename__ = "system_keys"
    __table_args__ = (UniqueConstraint("name", name="uq_system_keys_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
