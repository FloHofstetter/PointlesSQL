"""Shared serialization helpers for the ingest routes.

The redaction shim is the load-bearing piece: it replaces every
``secrets`` value with ``"***"`` on every API GET so credentials never
leave the server.  On PATCH the route layer detects the ``"***"``
sentinel and keeps the previously-stored value — mirroring the
audit-sink pattern.
"""

from __future__ import annotations

import json
from typing import Any

from pointlessql.models import IngestSource

# Sentinel value that the API GET path returns in place of any
# secret value.  PATCH-side, callers may echo it back to mean
# "leave this secret unchanged".
SECRETS_REDACTED_SENTINEL = "***"


def redact_secrets(secrets_json: str) -> dict[str, str]:
    """Return the secrets dict with every value replaced by ``***``.

    Args:
        secrets_json: The raw JSON-encoded secrets blob on the row.

    Returns:
        Dict with the same keys but redacted string values.  Empty
        dict on malformed input.
    """
    if not secrets_json:
        return {}
    try:
        data = json.loads(secrets_json)
    except ValueError, TypeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for key in data:  # type: ignore[reportUnknownVariableType]
        out[str(key)] = SECRETS_REDACTED_SENTINEL  # type: ignore[reportUnknownArgumentType]
    return out


def merge_patch_secrets(existing_json: str, patch_secrets: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a PATCH's secret values into the existing stored blob.

    Values equal to :data:`SECRETS_REDACTED_SENTINEL` are kept from
    the stored row (they came round-trip from a GET — the user did not
    actually re-enter the secret).  All other values overwrite.

    Args:
        existing_json: The currently-stored ``secrets`` JSON column.
        patch_secrets: The PATCH body's ``secrets`` dict (may be None).

    Returns:
        A plain dict ready to be ``json.dumps``-ed back into the row.
    """
    try:
        existing_any: Any = json.loads(existing_json or "{}")
    except ValueError, TypeError:
        existing_any = {}
    existing: dict[str, Any] = (
        {str(k): v for k, v in existing_any.items()}  # type: ignore[union-attr]
        if isinstance(existing_any, dict)
        else {}
    )
    if not patch_secrets:
        return existing
    merged = dict(existing)
    for key, value in patch_secrets.items():
        if value == SECRETS_REDACTED_SENTINEL:
            continue
        merged[str(key)] = value
    return merged


def serialize_source(row: IngestSource) -> dict[str, Any]:
    """Project an :class:`IngestSource` into a JSON-ready dict.

    Secrets are redacted; config and table_mappings round-trip
    untouched.

    Args:
        row: ORM row.

    Returns:
        Dict suitable for ``json.dumps``.
    """
    try:
        config = json.loads(row.config or "{}")
    except ValueError, TypeError:
        config = {}
    try:
        mappings = json.loads(row.table_mappings or "[]")
    except ValueError, TypeError:
        mappings = []
    return {
        "id": int(row.id),
        "workspace_id": int(row.workspace_id),
        "owner_user_id": int(row.owner_user_id),
        "name": row.name,
        "kind": row.kind,
        "config": config,
        "secrets": redact_secrets(row.secrets or "{}"),
        "table_mappings": mappings,
        "job_id": int(row.job_id) if row.job_id is not None else None,
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
