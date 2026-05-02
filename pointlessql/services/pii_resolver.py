"""Cached PII-tag lookups against soyuz-catalog.

Lineage value-changes and any future audit surface
that renders raw cell values needs to know whether a column is
flagged ``PII`` so it can mask the cleartext from non-admin
viewers.  Soyuz exposes a per-securable tags surface (``GET
/tags/column/{cat.sch.tbl.col}``) which is the source of truth.

A naive "ask soyuz on every render" loop would issue N+1 HTTP
requests per row-trace page (one per value-change row), so this
module wraps the lookup in a TTL cache:

* keyed by ``(table_fqn, column)``;
* default 600 s TTL, configurable via
  :class:`pointlessql.settings.AuditSettings.pii_cache_ttl_seconds`;
* :func:`invalidate` clears one entry; :func:`invalidate_all`
  drains the cache (the eventual tag-edit UI calls one of these
  after a successful PATCH).

Failure mode: any soyuz error (transport, timeout, 4xx, 5xx)
returns ``False`` and is logged.  "Mask on uncertainty" would
surface fewer leaks but also a lot of noisy false positives on a
soyuz outage; the conservative + auditable behaviour is to render
cleartext when the tag system is unavailable, log the failure,
and let ops triage.  The default for :attr:`pii_mask_default`
stays ``True``; this module's job is "answer the truthy question
fast", not "set policy".
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Module-level TTL cache: ``(table_fqn, column) → (expiry_epoch, is_pii)``.
_cache: dict[tuple[str, str], tuple[float, bool]] = {}
_cache_lock = asyncio.Lock()


def _is_truthy_pii_tag(key: str, value: Any) -> bool:
    """Decide whether a soyuz tag indicates PII for the column.

    Liberally accept several common spellings — operators may tag
    ``pii=true``, ``PII=yes``, or even ``pii_class=email``.  Any
    tag whose key contains the case-insensitive substring "pii"
    with a non-falsy value classifies the column as PII.

    Args:
        key: Tag key from soyuz.
        value: Tag value (string/bool/None per the API).

    Returns:
        ``True`` iff the tag fires the masking policy.
    """
    if "pii" not in key.lower():
        return False
    if value is None:
        # Bare presence of a "pii" key (no value) is a strong
        # enough signal.
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    sval = str(value).strip().lower()
    if not sval:
        return True
    return sval not in {"false", "no", "0", "n", "off"}


async def is_column_pii(
    uc: Any,
    table_fqn: str,
    column: str,
    *,
    ttl_seconds: int = 600,
) -> bool:
    """Return ``True`` iff the column is tagged PII in soyuz.

    Args:
        uc: A :class:`UnityCatalogClient` (or any object with the
            same ``async get_tags(securable_type, full_name)``
            shape) — typically ``app.state.uc_client``.
        table_fqn: Three-part UC name (``catalog.schema.table``).
        column: Column name.
        ttl_seconds: Cache lifetime.  Pass the value from
            :class:`AuditSettings.pii_cache_ttl_seconds`.

    Returns:
        ``True`` iff at least one tag on the column matches the
        :func:`_is_truthy_pii_tag` rule, ``False`` otherwise.
        Errors (no UC client, transport failure, 4xx/5xx) return
        ``False`` after a warning log.
    """
    if uc is None or not table_fqn or not column:
        return False
    full_name = f"{table_fqn}.{column}"
    key = (table_fqn, column)
    now = time.time()
    async with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
    try:
        tags = await uc.get_tags("column", full_name)
    except Exception as exc:  # noqa: BLE001 — masking must never break a render
        logger.warning("pii_resolver: get_tags(column, %s) failed: %s", full_name, exc)
        return False
    is_pii = False
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            tag_key = str(tag.get("key") or "")
            if _is_truthy_pii_tag(tag_key, tag.get("value")):
                is_pii = True
                break
    expiry = now + max(1, ttl_seconds)
    async with _cache_lock:
        _cache[key] = (expiry, is_pii)
    return is_pii


async def resolve_many(
    uc: Any,
    pairs: list[tuple[str, str]],
    *,
    ttl_seconds: int = 600,
) -> dict[tuple[str, str], bool]:
    """Resolve ``(table, column)`` pairs into a PII map in one pass.

    Used by the row-trace pre-render to avoid N round-trips when a
    page has many cells from the same table.  The cache layer
    deduplicates repeat keys before issuing soyuz calls.

    Args:
        uc: UnityCatalogClient (or compatible).
        pairs: Iterable of ``(table_fqn, column)`` tuples.  May
            contain duplicates — they collapse via the cache.
        ttl_seconds: Cache lifetime forwarded to
            :func:`is_column_pii`.

    Returns:
        Dict mapping each unique input pair to its PII verdict.
    """
    unique = list({(t, c) for t, c in pairs if t and c})
    results: dict[tuple[str, str], bool] = {}
    for table_fqn, column in unique:
        results[(table_fqn, column)] = await is_column_pii(
            uc, table_fqn, column, ttl_seconds=ttl_seconds
        )
    return results


def invalidate(table_fqn: str, column: str) -> None:
    """Drop one cache entry — call after a tag-edit UI write.

    Args:
        table_fqn: Three-part UC name.
        column: Column name.
    """
    _cache.pop((table_fqn, column), None)


def invalidate_all() -> None:
    """Drain the entire cache.

    Useful for tests and for the rare admin "I just bulk-imported
    100 PII tags, please re-resolve everything" path.
    """
    _cache.clear()
