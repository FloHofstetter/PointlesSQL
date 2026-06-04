"""Shared helpers for the admin API-key routes.

``serialize`` projects an ``ApiKey`` row to JSON; ``api_key_by_name``
resolves a live (non-revoked) key by name or raises 404.  Both are used
across the per-concern route modules in this package.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from pointlessql.exceptions import CatalogNotFoundError


def serialize(row: Any) -> dict[str, Any]:
    """Project an :class:`ApiKey` ORM row to a JSON-safe dict.

    Args:
        row: Detached ORM row from
            :func:`pointlessql.services.api_keys.list_api_keys` /
            :func:`create_api_key`.

    Returns:
        ``{name, secret_prefix, supervisor, auditor, created_at,
        revoked_at, last_used_at}``.  Plaintext secret is never
        included.
    """
    return {
        "name": row.name,
        "secret_prefix": row.secret_prefix,
        "supervisor": bool(row.supervisor),
        "auditor": bool(getattr(row, "auditor", False)),
        "lineage_inbound": bool(getattr(row, "lineage_inbound", False)),
        "analyst": bool(getattr(row, "analyst", False)),
        "sql_execute": bool(getattr(row, "sql_execute", False)),
        "token_format": getattr(row, "token_format", "legacy") or "legacy",
        "token_env": getattr(row, "token_env", "legacy") or "legacy",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "last_used_at": (row.last_used_at.isoformat() if row.last_used_at else None),
        "expires_at": (row.expires_at.isoformat() if getattr(row, "expires_at", None) else None),
        "rotated_at": (row.rotated_at.isoformat() if getattr(row, "rotated_at", None) else None),
        "grace_until": (row.grace_until.isoformat() if getattr(row, "grace_until", None) else None),
        "quarantined_at": (
            row.quarantined_at.isoformat() if getattr(row, "quarantined_at", None) else None
        ),
        "quarantine_reason": getattr(row, "quarantine_reason", None),
        "rotated_from_id": getattr(row, "rotated_from_id", None),
    }


def api_key_by_name(request: Request, name: str) -> Any:
    """Resolve an :class:`ApiKey` row by name; raises 404 when missing."""
    from sqlalchemy import select

    from pointlessql.models import ApiKey

    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.revoked_at is not None:
            raise CatalogNotFoundError(f"api_key {name!r} not found or revoked")
        session.expunge(row)
        return row
