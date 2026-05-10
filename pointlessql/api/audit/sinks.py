"""Admin CRUD for the ``audit_sinks`` table.

Six JSON endpoints, all gated by :func:`require_admin`:

* ``GET /api/admin/audit-sinks`` — list every sink, active and inactive.
* ``POST /api/admin/audit-sinks`` — create a sink with type-specific
  config.  Secret values inside ``config_json`` (HMAC, AWS access
  keys) round-trip in cleartext at create time only.
* ``PATCH /api/admin/audit-sinks/{id}`` — sparse update.  Per-key
  patch on the JSON config so admins can rotate a secret without
  re-sending the bucket name.
* ``DELETE /api/admin/audit-sinks/{id}`` — hard-delete.  Historical
  fan-out lines on ``governance_events.delivered_to_json`` survive
  deletion because the sink's id + name are stamped on each entry.
* ``POST /api/admin/audit-sinks/{id}/test`` — fire one synthetic
  ``pointlessql.audit_sink.test`` envelope at the sink so an admin
  can verify connectivity from the UI without waiting for a real
  governance event.
* ``GET /api/admin/audit-sinks/recent-events`` — last 50
  ``governance_events`` rows for the cockpit panel.

The shape mirrors :mod:`pointlessql.api.review_destinations_routes`
so future admins recognise the affordances at a glance.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import Workspace
from pointlessql.models.audit_sinks import SINK_TYPES, AuditSink, GovernanceEvent

router = APIRouter(tags=["admin-audit-sinks"])

_MAX_NAME = 64
_MAX_CONFIG_BYTES = 8192
_SENSITIVE_KEYS: frozenset[str] = frozenset({"hmac_secret", "secret_access_key", "session_token"})


def _loads_obj(raw: str | None) -> dict[str, Any]:
    """Decode *raw* JSON into a dict; return ``{}`` on parse error or non-object."""
    if not raw:
        return {}
    try:
        decoded: Any = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else {}


def _loads_list(raw: str | None) -> list[Any]:
    """Decode *raw* JSON into a list; return ``[]`` on parse error or non-array."""
    if not raw:
        return []
    try:
        decoded: Any = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return cast(list[Any], decoded) if isinstance(decoded, list) else []


def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Replace sensitive keys in *config* with ``"<redacted>"``.

    Args:
        config: The decoded sink config.

    Returns:
        A copy of *config* with the same keys, sensitive values
        replaced by the string ``"<redacted>"`` so admins see
        whether a secret is set without leaking it.
    """
    out = dict(config)
    for k in list(out.keys()):
        if k in _SENSITIVE_KEYS and out[k]:
            out[k] = "<redacted>"
    return out


def _serialize(row: AuditSink) -> dict[str, Any]:
    """Project an :class:`AuditSink` ORM row to a JSON-safe dict.

    Args:
        row: ORM row.

    Returns:
        ``{id, name, type, config (redacted), is_active,
        event_types, workspace_filter, created_at}``.
        ``workspace_filter`` is ``None`` for install-global sinks
        (the default) or a list of workspace IDs.
    """
    cfg = _loads_obj(row.config_json or "{}")
    event_types = _loads_list(row.event_types_json)
    ws_decoded = _loads_list(row.workspace_filter)
    workspace_filter: list[int] | None = [int(x) for x in ws_decoded] if ws_decoded else None
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "config": _redact_config(cfg),
        "is_active": bool(row.is_active),
        "event_types": event_types,
        "workspace_filter": workspace_filter,
        "created_at": row.created_at.astimezone(datetime.UTC).isoformat(),
    }


def _validate_name(value: Any) -> str:
    """Return *value* as a non-empty trimmed string ≤ 64 chars."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("name must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > _MAX_NAME:
        raise ValidationError(f"name must be ≤ {_MAX_NAME} chars")
    return cleaned


def _validate_type(value: Any) -> str:
    """Return *value* as one of the three allowed sink types."""
    if not isinstance(value, str) or value not in SINK_TYPES:
        raise ValidationError(f"type must be one of {sorted(SINK_TYPES)}")
    return value


def _validate_config(value: Any, *, sink_type: str) -> dict[str, Any]:
    """Return *value* as a config dict with type-specific required keys.

    Args:
        value: Caller-supplied config.  Either a JSON-encoded string
            or a dict.
        sink_type: One of :data:`SINK_TYPES`.  Determines the
            required-key check.

    Returns:
        Decoded config dict.

    Raises:
        ValidationError: On bad shape or missing required keys.
    """
    decoded: Any
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"config must be valid JSON: {exc}") from exc
    elif isinstance(value, dict):
        decoded = cast(Any, value)
    else:
        raise ValidationError("config must be a JSON object or a JSON-encoded string")
    if not isinstance(decoded, dict):
        raise ValidationError("config must decode to a JSON object")
    decoded_dict = cast(dict[str, Any], decoded)
    serialised = json.dumps(decoded_dict)
    if len(serialised.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise ValidationError(f"config must be ≤ {_MAX_CONFIG_BYTES} bytes serialised")
    required = {
        "webhook": ("url",),
        "s3": ("bucket", "region", "access_key_id", "secret_access_key"),
        "aws_cloudtrail": ("region", "channel_arn", "access_key_id", "secret_access_key"),
    }[sink_type]
    missing = [k for k in required if not decoded_dict.get(k)]
    if missing:
        raise ValidationError(f"{sink_type} config requires non-empty {sorted(missing)} keys")
    return decoded_dict


def _validate_event_types(value: Any) -> list[str]:
    """Return *value* as a list of event-type strings, or an empty list."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("event_types must be a list of strings")
    items = cast(list[Any], value)
    out: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError("event_types entries must be non-empty strings")
        out.append(item.strip())
    return out


def _validate_workspace_filter(
    value: Any,
    *,
    known_workspace_ids: set[int],
) -> list[int] | None:
    """Return *value* as a list of int workspace IDs, or ``None``.

    Args:
        value: Caller-supplied filter.  ``None`` or an empty list →
            install-global semantics (return ``None``).  Otherwise a
            list of ints; each must already exist in ``workspaces``.
        known_workspace_ids: Set of IDs that exist at validation time
            — admin pre-fetched once per request to bound DB hits.

    Returns:
        Normalised list of unique ints (sorted), or ``None`` when the
        caller asked for the install-global default.

    Raises:
        ValidationError: On bad shape or unknown workspace IDs.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValidationError("workspace_filter must be a list of integers or null")
    if not value:
        return None
    items = cast(list[Any], value)
    out: set[int] = set()
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValidationError("workspace_filter entries must be integers")
        if item not in known_workspace_ids:
            raise ValidationError(f"workspace_filter references unknown workspace_id={item}")
        out.add(item)
    return sorted(out)


@router.get("/api/admin/audit-sinks")
async def api_admin_list_audit_sinks(request: Request) -> dict[str, Any]:
    """List every audit sink, active and inactive."""
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(session.scalars(select(AuditSink).order_by(AuditSink.id.asc())).all())
        for row in rows:
            session.expunge(row)
    return {"sinks": [_serialize(row) for row in rows]}


@router.post("/api/admin/audit-sinks")
async def api_admin_create_audit_sink(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new audit sink.

    Args:
        request: Incoming FastAPI request.
        body: ``{name, type, config (object), event_types?, is_active?}``.

    Returns:
        Serialised sink row (sensitive keys in ``config`` are
        redacted; the cleartext config is *not* returned — admins
        already supplied it).

    Raises:
        ValidationError: On bound or shape violations.
    """
    require_admin(request)
    name = _validate_name(body.get("name"))
    sink_type = _validate_type(body.get("type"))
    config = _validate_config(body.get("config"), sink_type=sink_type)
    event_types = _validate_event_types(body.get("event_types"))
    is_active = bool(body.get("is_active", True))

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(select(AuditSink).where(AuditSink.name == name))
        if existing is not None:
            raise ValidationError(f"audit_sink with name {name!r} already exists")
        known_ws = set(session.scalars(select(Workspace.id)).all())
        workspace_filter = _validate_workspace_filter(
            body.get("workspace_filter"), known_workspace_ids=known_ws
        )
        row = AuditSink(
            name=name,
            type=sink_type,
            config_json=json.dumps(config),
            is_active=is_active,
            event_types_json=json.dumps(event_types) if event_types else None,
            workspace_filter=json.dumps(workspace_filter) if workspace_filter else None,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "audit_sink.created",
        f"audit_sink:{row.name}",
        {
            "type": sink_type,
            "is_active": is_active,
            "event_types": event_types,
            "workspace_filter": workspace_filter,
        },
    )
    return _serialize(row)


@router.patch("/api/admin/audit-sinks/{sink_id}")
async def api_admin_update_audit_sink(
    request: Request,
    sink_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Update a sink in place (sparse PATCH).

    The ``config`` field merges into the existing config rather than
    replacing it — admins can rotate ``secret_access_key`` without
    re-sending ``bucket``.  Pass ``{"config": null}`` to nuke and
    re-supply the full object.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(AuditSink, sink_id)
        if row is None:
            raise CatalogNotFoundError(f"audit_sink id={sink_id} not found")
        if "is_active" in body:
            row.is_active = bool(body["is_active"])
        if "event_types" in body:
            event_types = _validate_event_types(body["event_types"])
            row.event_types_json = json.dumps(event_types) if event_types else None
        if "workspace_filter" in body:
            known_ws = set(session.scalars(select(Workspace.id)).all())
            ws_filter = _validate_workspace_filter(
                body["workspace_filter"], known_workspace_ids=known_ws
            )
            row.workspace_filter = json.dumps(ws_filter) if ws_filter else None
        if "config" in body:
            existing_cfg = _loads_obj(row.config_json or "{}")
            patch = body["config"]
            if patch is None:
                merged: dict[str, Any] = {}
            elif isinstance(patch, dict):
                merged = {**existing_cfg, **patch}
            else:
                raise ValidationError("config must be a JSON object or null")
            validated = _validate_config(merged, sink_type=row.type)
            row.config_json = json.dumps(validated)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    redacted_changes = {k: v for k, v in body.items() if k != "config"}
    if "config" in body:
        config_patch = body["config"]
        config_keys: list[str] = []
        if isinstance(config_patch, dict):
            config_keys = sorted(cast(dict[str, Any], config_patch).keys())
        redacted_changes["config_keys_changed"] = config_keys
    await audit(
        request,
        "audit_sink.updated",
        f"audit_sink:{row.name}",
        redacted_changes,
    )
    return _serialize(row)


@router.delete("/api/admin/audit-sinks/{sink_id}")
async def api_admin_delete_audit_sink(request: Request, sink_id: int) -> dict[str, Any]:
    """Hard-delete a sink row."""
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(AuditSink, sink_id)
        if row is None:
            raise CatalogNotFoundError(f"audit_sink id={sink_id} not found")
        name = row.name
        session.delete(row)
        session.commit()
    await audit(
        request,
        "audit_sink.deleted",
        f"audit_sink:{name}",
    )
    return {"deleted": sink_id, "name": name}


@router.post("/api/admin/audit-sinks/{sink_id}/test")
async def api_admin_test_audit_sink(request: Request, sink_id: int) -> dict[str, Any]:
    """Fire one synthetic envelope at *sink_id* and return the dispatch result.

    The envelope's ``type`` is ``pointlessql.audit_sink.test`` so a
    receiver can filter test traffic from real governance events
    without parsing the data payload.  The function bypasses the
    ``audit_sinks`` event-type filter to guarantee delivery — admins
    asked for this fan-out explicitly.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(AuditSink, sink_id)
        if row is None:
            raise CatalogNotFoundError(f"audit_sink id={sink_id} not found")
        session.expunge(row)
    import uuid

    envelope = {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "source": "/pointlessql/audit-sinks/test",
        "type": "pointlessql.audit_sink.test",
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": str(sink_id),
        "data": {
            "sink_id": sink_id,
            "sink_name": row.name,
            "sink_type": row.type,
            "note": "synthetic test envelope from /api/admin/audit-sinks/test",
        },
    }
    # Bypass the standard dispatch filter — call the per-sink dispatcher directly
    from pointlessql.services.audit.sinks import dispatch_one

    ok = await dispatch_one(row, envelope)
    await audit(
        request,
        "audit_sink.tested",
        f"audit_sink:{row.name}",
        {"ok": ok},
    )
    return {"sink_id": sink_id, "name": row.name, "type": row.type, "ok": ok}


@router.get("/api/admin/audit-sinks/recent-events")
async def api_admin_recent_governance_events(request: Request) -> dict[str, Any]:
    """Last 50 ``governance_events`` rows in fired-at-desc order.

    Returned shape is intentionally narrow: the cockpit table
    surfaces ``event_type``, ``fired_at``, ``outcome``, and
    per-event drill-into-the-payload is a follow-up sprint.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(GovernanceEvent).order_by(GovernanceEvent.id.desc()).limit(50)
            ).all()
        )
        for row in rows:
            session.expunge(row)
    return {
        "events": [
            {
                "id": row.id,
                "event_id": row.event_id,
                "event_type": row.event_type,
                "fired_at": row.fired_at.astimezone(datetime.UTC).isoformat(),
                "outcome": row.outcome,
            }
            for row in rows
        ]
    }


__all__ = ["router"]
