"""Cross-route helpers shared by every ``/api/audit/*`` JSON endpoint.

Three concerns colocated here because every sub-module needs them:

* :func:`_resolve_workspace_lens` — the super-admin lens that the
  cockpit / Hermes audit tools / Grafana panels share.  Default is
  current-workspace; admins can request ``?workspace=all`` or
  ``?workspace=<slug>`` to escalate visibility.
* :func:`_parse_iso8601` — uniform ISO-8601 parse with UTC coercion;
  garbage input becomes a 422 so the cockpit ``?since=`` URL builder
  cannot silently bypass filters.
* :func:`_record_self` — writes one ``query_history`` row per
  audit-API call so the cockpit endpoints themselves stay visible in
  the cockpit (the "audit-of-audit" gap from the roadmap).

The helpers are public to the audit package but the leading underscore
keeps them out of the routes-level facade — direct consumers stay
inside ``pointlessql/api/audit/``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import get_optional_user, get_user
from pointlessql.exceptions import PermissionDeniedError, ValidationError
from pointlessql.services.query_history import record_query
from pointlessql.types import QueryStatus, ReadKind

logger = logging.getLogger(__name__)


def resolve_workspace_lens(request: Request, override: str | None) -> tuple[int | None, str]:
    """Pick the audit query's workspace filter from the optional override.

    Implements the super-admin lens.  Three outcomes:

    * ``override is None`` (or whitespace-only) — scope to the request's
      resolved workspace (``request.state.workspace_id``).  The default
      cockpit experience.
    * ``override == "all"`` — admin-only.  Returns ``(None, "all")`` to
      tell :mod:`audit_aggregator` to skip the workspace filter.  Logs
      a ``read_kind="audit_api_cross_workspace"`` row downstream so
      the cross-workspace probe is observable.
    * ``override == "<slug>"`` — admin-only.  Resolves the slug to an
      ``id`` and scopes to it.  A non-admin caller asking for any
      workspace other than their resolved one gets a 403.

    Args:
        request: Incoming FastAPI request.
        override: Raw ``?workspace=`` query value.

    Returns:
        ``(workspace_id, mode)`` — ``workspace_id`` is ``None`` for
        the cross-workspace lens, an int otherwise; ``mode`` is one
        of ``"current"`` / ``"all"`` / ``"named"`` for telemetry.

    Raises:
        PermissionDeniedError: 403 when the caller is not a tenant
            admin and asked for ``"all"`` or a different workspace's
            slug.
        ValidationError: Slug doesn't resolve.
    """
    cleaned = (override or "").strip()
    current_id = int(getattr(request.state, "workspace_id", 1) or 1)
    if not cleaned:
        return current_id, "current"

    user = get_optional_user(request)
    is_admin = bool(user and user.get("is_admin"))

    if cleaned.lower() == "all":
        if not is_admin:
            raise PermissionDeniedError("?workspace=all requires admin")
        return None, "all"

    # Slug → id
    from pointlessql.services.workspace import _crud as workspaces_service

    factory = request.app.state.session_factory
    ws = workspaces_service.get_workspace_by_slug(factory, slug=cleaned)
    if ws is None:
        raise ValidationError(f"workspace {cleaned!r} not found")
    if ws.id != current_id and not is_admin:
        raise PermissionDeniedError("?workspace=<slug> for a different workspace requires admin")
    return ws.id, "named"


def parse_iso8601(name: str, value: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 query-string param, raising 422 on garbage.

    Naive timestamps are coerced to UTC so a caller passing
    ``?since=2026-04-20`` doesn't silently slide by their local
    offset.

    Args:
        name: Human-readable param name for the error message.
        value: Raw query-string value; ``None`` and empty strings
            short-circuit to ``None``.

    Returns:
        Parsed timezone-aware :class:`datetime`, or ``None`` when
        the param was unset.

    Raises:
        ValidationError: ``value`` is non-empty but not parseable.
    """
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


def record_self(
    request: Request,
    *,
    endpoint: str,
    params: dict[str, Any],
    started_at: datetime.datetime,
    read_kind: ReadKind = ReadKind.AUDIT_API,
) -> None:
    """Persist a ``query_history`` row for one ``/api/audit/*`` call.

    Best-effort — a failure to record the audit-of-audit row should
    never fail the actual audit response (the operator on-call
    needs the data more than they need a self-tracking row).

    Args:
        request: FastAPI request, carrying the authenticated user.
        endpoint: Stable string identifier for the route, e.g.
            ``"/api/audit/summary"``.
        params: Query-string params that were honoured (so a
            "weirdly-empty result" can be re-traced via the params
            the cockpit caller actually sent).
        started_at: Wall-clock instant the route began handling.
        read_kind: Defaults to ``"audit_api"``; cross-workspace
            lens calls pass ``"audit_api_cross_workspace"`` so the
            audit-of-audit aggregation can flag tenant-admin
            escalations into the god-eye view.
    """
    user = get_user(request)
    finished_at = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    sql_text = f"-- audit_api: {endpoint} {json.dumps(params, sort_keys=True, default=str)}"
    try:
        record_query(
            factory,
            user_id=int(user.get("id") or 0),
            user_email=str(user.get("email") or "anonymous"),
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status=QueryStatus.SUCCEEDED,
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[],
            agent_run_id=None,
            read_kind=read_kind,
        )
    except Exception:  # noqa: BLE001 — audit-of-audit must never break the audit response
        logger.exception(
            "audit_api: failed to self-track",
            extra={"endpoint": endpoint},
        )
