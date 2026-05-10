"""Async audit + query-history record helpers used by the route layer.

Every mutation route calls :func:`audit` after the underlying
service committed; every SQL execute / cancel / export call goes
through :func:`record_query_async` so the ``/queries`` page sees
every attempt.

Both functions dispatch their write to :func:`asyncio.to_thread` so
the request handler never blocks on the DB round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import client_ip, effective_principal, get_user
from pointlessql.services import audit as audit_service
from pointlessql.services import query_history as query_history_service
from pointlessql.types import QueryStatus, ReadKind, RunId

logger = logging.getLogger(__name__)


def effective_agent_run_id(request: Request) -> str | None:
    """Resolve the active ``agent_run_id`` for the current request.

    Mirrors the X-Principal precedence: the ``X-Agent-Run-Id`` HTTP
    header wins over the ``POINTLESSQL_AGENT_RUN_ID`` env var, both
    are case-insensitive on the env-var side.  Returned value is
    whitespace-stripped; empty / missing collapses to ``None``.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The resolved run-UUID string, or ``None`` when no run is
        in scope.
    """
    header = request.headers.get("X-Agent-Run-Id")
    if isinstance(header, str) and header.strip():
        return header.strip()
    env = os.environ.get("POINTLESSQL_AGENT_RUN_ID")
    if env and env.strip():
        return env.strip()
    return None


async def record_query_async(
    request: Request,
    *,
    sql_text: str,
    started_at: datetime,
    finished_at: datetime,
    status: QueryStatus,
    row_count: int | None,
    duration_ms: int | None,
    referenced_tables: list[str],
    error_message: str | None = None,
    agent_run_id: str | None = None,
    read_kind: ReadKind | str = ReadKind.SQL_EXECUTE,
) -> int | None:
    """Persist a query-history row without blocking the loop.

    Mirrors :func:`audit` for the dedicated ``query_history``
    surface.  The INSERT happens inside :func:`asyncio.to_thread`
    so the request handler continues serving other requests during
    the write.  Swallows DB errors after logging — a lost history
    row must never mask a successful (or failing) query response.

    Args:
        request: The incoming FastAPI request.
        sql_text: Verbatim user-submitted SQL.
        started_at: When the route began handling the request.
        finished_at: When the route's try/except exited.
        status: ``"succeeded"`` / ``"failed"`` / ``"cancelled"``.
        row_count: Final row count or ``None`` on failure.
        duration_ms: DuckDB wall-clock time or ``None`` on failure.
        referenced_tables: Three-part names extracted from the parse.
            May be empty if the SQL did not parse.
        error_message: Exception detail for failures; ``None`` on
            success.
        agent_run_id: Explicit run-UUID override.  When ``None`` the
            resolution falls back to :func:`effective_agent_run_id`
            so callers in the route layer don't need to thread the
            header through.
        read_kind: Discriminator stored on the row (default
            ``ReadKind.SQL_EXECUTE`` matches the legacy SELECT
            path).  Phase 63 dispatcher passes ``"sql_dml"`` for
            INSERT/UPDATE/DELETE/MERGE and ``"sql_ddl"`` for
            DROP/CREATE so :file:`/queries` can filter editor
            traffic by family.

    Returns:
        The new ``query_history.id`` on success; ``None`` if no
        session factory is bound or the INSERT failed.
    """
    user = get_user(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return None
    request_id = getattr(request.state, "request_id", None)
    # Prefer X-Principal header over cookie user so a Hermes-driven
    # query is attributed to the agent's principal, not the
    # (probably-empty) session-cookie user on the agent side.
    attributed_email = effective_principal(request) or user["email"]
    # Explicit kwarg wins over header/env so internal callers (e.g.
    # PQL primitives via the forced audit trail) can pass the run
    # id without depending on request headers.
    resolved_run_id = agent_run_id or effective_agent_run_id(request)
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    resolved_read_kind = (
        read_kind if isinstance(read_kind, ReadKind) else ReadKind(read_kind)
    )
    try:
        return await asyncio.to_thread(
            query_history_service.record_query,
            factory,
            user_id=user["id"],
            user_email=attributed_email,
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            row_count=row_count,
            duration_ms=duration_ms,
            referenced_tables=referenced_tables,
            error_message=error_message,
            request_id=request_id,
            agent_run_id=RunId(resolved_run_id) if resolved_run_id else None,
            workspace_id=workspace_id,
            read_kind=resolved_read_kind,
        )
    except Exception:  # noqa: BLE001 — never mask the query response
        logger.exception("failed to record query_history row")
        return None


async def audit(
    request: Request,
    action: str,
    target: str,
    detail: str | dict[str, Any] | None = None,
) -> None:
    """Write an audit log entry for the current user.

    The insert is dispatched to :func:`asyncio.to_thread` so the
    HTTP request handler never blocks on the DB round-trip.

    Bearer-authenticated requests carry ``user_id == 0`` (no cookie
    user) but expose ``request.state.api_key_name``; the row is
    written with ``actor_role="system"`` and
    ``user_email=api_key:<name>`` when no ``X-Principal`` header
    re-attributes to a human.

    Args:
        request: The incoming HTTP request.
        action: Short verb describing the action (e.g.
            ``update_catalog``).
        target: Identifier of the affected resource (e.g.
            ``catalog:my_cat``).
        detail: Optional JSON-encodable dict or plain string with
            extra context.
    """
    user = get_user(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return
    api_key_name: str | None = getattr(request.state, "api_key_name", None)
    if not user["id"] and api_key_name is None:
        return
    if api_key_name is not None:
        role = "system"
    else:
        role = "admin" if user.get("is_admin") else "user"
    # ``X-Principal`` overrides the cookie email so the audit trail
    # points at the agent's principal when Hermes is making the
    # call.  ``user_id`` stays the cookie user's id — that is the
    # actor whose session signed the request, even when they're
    # acting on someone else's behalf.
    attributed_email = (
        effective_principal(request)
        or user["email"]
        or (f"api_key:{api_key_name}" if api_key_name else "")
    )
    detail_payload: str | dict[str, Any] | None = detail
    if api_key_name is not None:
        merged: dict[str, Any] = {"api_key": api_key_name}
        if isinstance(detail, dict):
            merged.update(detail)
        elif isinstance(detail, str) and detail:
            merged["note"] = detail
        detail_payload = merged
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    await asyncio.to_thread(
        audit_service.log_action,
        factory,
        user["id"],
        attributed_email,
        action,
        target,
        detail_payload,
        actor_role=role,
        client_ip=client_ip(request),
        workspace_id=workspace_id,
    )
