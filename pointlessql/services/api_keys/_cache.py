"""KeyEntry + the shared in-memory verify-bearer cache.

The cache is a module-level ``dict`` keyed on the SHA-256 of the
presented secret (TTL 60 s).  It lives here so the verify path and the
CRUD path (which invalidates it on writes) share one object by import
reference — :func:`invalidate_cache` and the verify path only ever
*mutate* it, never reassign it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class KeyEntry:
    """The fields the middleware needs to authorise a Bearer request.

    Every API key pins to exactly one workspace, and Bearer-authed
    requests inherit that workspace as their resolved context.
    Existing keys backfill to the default workspace (id=1) by the
    bootstrap migration so this attribute is always populated.
    """

    name: str
    supervisor: bool
    auditor: bool = False
    lineage_inbound: bool = False
    analyst: bool = False
    sql_execute: bool = False
    workspace_id: int = 1
    id: int = 0
    created_by_user_id: int | None = None


CACHE_TTL_SECONDS = 60.0
resolve_cache: dict[str, tuple[KeyEntry, float]] = {}


def hash_secret(secret: str) -> str:
    """Return the SHA-256 hex digest of *secret* (UTF-8 encoded)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def as_aware_utc(value: datetime | None) -> datetime | None:
    """Coerce a possibly-naive timestamp to a UTC-aware ``datetime``.

    SQLite returns ``DateTime(timezone=True)`` columns as naive ``datetime``
    on read; Postgres returns them aware.  lifecycle gates
    compare against ``datetime.now(UTC)`` (aware), which would raise
    ``TypeError`` on the SQLite path.  Treating naive timestamps as UTC
    matches what we wrote and unifies the two dialects.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def invalidate_cache() -> None:
    """Clear the in-memory verify-bearer cache.

    Call after any admin write (:func:`create_api_key`,
    :func:`revoke_api_key`) so a freshly-rotated key takes effect on
    the next request rather than after the TTL.
    """
    resolve_cache.clear()
