"""Query history + saved queries routes.

Owns the query-history read endpoints (``/api/queries``,
``/api/queries/{id}``, ``/api/queries/{id}/chart-config``) plus
the full saved-queries CRUD (``/api/saved-queries`` GET/POST +
``/{slug}`` GET/PATCH/DELETE) and the ``/queries`` HTML page that
lists them.

Visibility model:

* ``query_history`` rows: non-admin sees only their own; admin sees
  every row.  ``user_id=`` query param is clamped to caller for
  non-admin so the param can't be used to probe other people's
  history.
* ``saved_queries`` rows: non-admin sees their own + every row with
  ``is_shared=True``; admin sees all.  Mutations are owner+admin
  only; missing-vs-forbidden collapses to 404 so private slugs
  cannot be probed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import ValidationError
from pointlessql.services import query_history as query_history_service
from pointlessql.services import saved_queries as saved_queries_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["queries"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def parse_since(raw: str | None) -> datetime | None:
    """Map a ``?since=`` query param to a cutoff datetime.

    Accepts ``24h``, ``7d``, ``30d``, ``all``, or ``None``.  Any other
    value maps to ``None`` (no filter) — invalid input should never
    reject the whole page.

    Args:
        raw: The raw query-string value.

    Returns:
        The cutoff :class:`datetime` in UTC, or ``None`` for
        ``"all"`` / unparseable / missing.
    """
    if not raw or raw == "all":
        return None
    mapping = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = mapping.get(raw)
    if delta is None:
        return None
    return datetime.now(UTC) - delta


@router.get("/api/queries")
async def api_list_queries(
    request: Request,
    *,
    user_id: int | None = None,
    status: str | None = None,
    since: str | None = None,
    agent_run_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent query-history rows as JSON.

    Non-admin callers see only their own rows — the ``user_id``
    query param is clamped to the caller's ID regardless of what
    was requested, mirroring the visibility rule applied on
    ``/api/jobs``.  Admin can pass ``user_id=123`` to scope or
    ``None`` to see everyone.

    Args:
        request: Incoming request (for the current user).
        user_id: Optional user-ID filter (admin only).
        status: Optional status filter.
        since: Window string (``24h`` / ``7d`` / ``30d`` / ``all``).
        agent_run_id: Optional run-UUID filter.
        limit: Hard row cap (default 200).

    Returns:
        A list of history dicts — see
        :func:`pointlessql.services.query_history.list_queries`.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = get_user(request)
    if not user.get("is_admin"):
        user_id = user["id"]
    effective_limit = max(1, min(int(limit), 1000))
    cleaned_run_id = (
        agent_run_id.strip() if isinstance(agent_run_id, str) and agent_run_id.strip() else None
    )
    return await asyncio.to_thread(
        query_history_service.list_queries,
        factory,
        user_id=user_id,
        status=status,
        since=parse_since(since),
        agent_run_id=cleaned_run_id,
        limit=effective_limit,
    )


@router.get("/api/queries/{history_id}")
async def api_get_query(request: Request, history_id: int) -> dict[str, Any]:
    """Return a single ``query_history`` row as JSON.

    Used by the chart-replay flow: the editor fetches a row by id
    to seed its chart config when the user opens a deep link.  404
    collapses ``missing`` and ``forbidden`` so an unprivileged
    caller cannot probe IDs.

    Args:
        request: Incoming request (for the current user).
        history_id: ``query_history.id`` to fetch.

    Returns:
        The history row dict.

    Raises:
        CatalogNotFoundError: If the row is missing or invisible.
    """  # noqa: DOC502,DOC503 — raised below
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    user = get_user(request)
    row = await asyncio.to_thread(
        query_history_service.get_by_id,
        factory,
        history_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if row is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    return row


@router.patch("/api/queries/{history_id}/chart-config")
async def api_update_query_chart_config(
    request: Request,
    history_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Persist the user's chart selection for a history row.

    The body carries ``chart_config`` as either a dict (stored
    canonically as ``json.dumps``-serialised text) or ``null`` to
    clear the persisted selection.  Only the row owner and admin
    users may mutate.

    Args:
        request: Incoming request.
        history_id: ``query_history.id`` to update.
        body: Mapping with a ``chart_config`` key carrying either a
            dict ``{type, x, y}`` or ``null``.

    Returns:
        The updated history row dict.

    Raises:
        CatalogNotFoundError: If the row is missing or not owned by
            the caller (admins exempt).
        ValidationError: If ``chart_config`` is present but is neither
            a mapping nor ``null``.
    """  # noqa: DOC502,DOC503 — raised below
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    user = get_user(request)
    payload = body or {}
    raw = payload.get("chart_config")
    if raw is None:
        serialised: str | None = None
    elif isinstance(raw, dict):
        serialised = json.dumps(raw, separators=(",", ":"), sort_keys=True)
    else:
        raise ValidationError("chart_config must be an object or null.")
    row = await asyncio.to_thread(
        query_history_service.update_chart_config,
        factory,
        history_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        chart_config=serialised,
    )
    if row is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    await audit(
        request,
        "query.chart_config_updated",
        f"query_history:{history_id}",
        {"cleared": serialised is None},
    )
    return row


@router.get("/queries", response_class=HTMLResponse)
async def queries_page(
    request: Request,
    agent_run_id: str | None = None,
) -> HTMLResponse:
    """Render the query history page.

    Pre-loads the initial history slice server-side so the page
    paints without waiting on a second round-trip; the list-table
    Alpine component then takes over for chip filtering and sort.

    When an ``agent_run_id`` query param is present the pre-loaded
    slice scopes to that run only and the page surfaces a
    dismissable filter pill so users see they're inside a sub-view.

    Args:
        request: The incoming FastAPI request.
        agent_run_id: Optional run-UUID filter via the URL query
            string (typically arrived from a run-detail "Queries"
            tab link).

    Returns:
        The rendered HTML page.
    """
    factory = getattr(request.app.state, "session_factory", None)
    user = get_user(request)
    entries: list[dict[str, Any]] = []
    cleaned_run_id = (
        agent_run_id.strip() if isinstance(agent_run_id, str) and agent_run_id.strip() else None
    )
    if factory is not None:
        user_filter: int | None = None if user.get("is_admin") else user["id"]
        entries = await asyncio.to_thread(
            query_history_service.list_queries,
            factory,
            user_id=user_filter,
            agent_run_id=cleaned_run_id,
            limit=200,
        )
    return _templates(request).TemplateResponse(
        request,
        "pages/queries.html",
        {
            "entries": entries,
            "agent_run_filter": cleaned_run_id,
            "active_page": "queries",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


# -- saved queries ---------------------------------------------------------


@router.get("/api/saved-queries")
async def api_list_saved_queries(request: Request) -> list[dict[str, Any]]:
    """Return every saved query visible to the current user.

    Admin sees all rows; non-admin sees their own + every row
    with ``is_shared = True``.  Ordered by ``updated_at`` so the
    most recent edits float to the top.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = get_user(request)
    return await asyncio.to_thread(
        saved_queries_service.list_visible,
        factory,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )


@router.post("/api/saved-queries")
async def api_create_saved_query(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new saved query owned by the current user.

    Args:
        request: The incoming FastAPI request.
        body: JSON body with ``title``, ``sql`` (or ``sql_text``),
            optional ``description`` and ``is_shared``.

    Returns:
        The serialised row as a dict.

    Raises:
        ValidationError: If ``title`` or the SQL field is missing
            / empty.
    """  # noqa: DOC502 — raised by services.saved_queries.create_saved_query
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ValidationError("Saved queries unavailable: no session factory bound.")
    user = get_user(request)
    payload = body or {}
    title = payload.get("title", "")
    description = payload.get("description")
    sql_text = payload.get("sql_text") or payload.get("sql") or ""
    is_shared = bool(payload.get("is_shared", False))
    row = await asyncio.to_thread(
        saved_queries_service.create_saved_query,
        factory,
        owner_id=user["id"],
        title=title if isinstance(title, str) else "",
        description=description if isinstance(description, str) else None,
        sql_text=sql_text if isinstance(sql_text, str) else "",
        is_shared=is_shared,
    )
    action = "query.shared" if row["is_shared"] else "query.saved"
    await audit(request, action, f"saved_query:{row['slug']}", {"title": row["title"]})
    return row


@router.get("/api/saved-queries/{slug}")
async def api_get_saved_query(request: Request, slug: str) -> dict[str, Any]:
    """Return a saved query by slug or 404 if hidden/missing.

    Args:
        request: The incoming request.
        slug: The saved-query slug.

    Returns:
        The serialised row.

    Raises:
        CatalogNotFoundError: If the slug does not exist or the
            current user cannot see it.  We collapse "not found"
            and "forbidden" so private slugs are not discoverable.
    """  # noqa: DOC502 — CatalogNotFoundError raised via module import below
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = get_user(request)
    row = await asyncio.to_thread(
        saved_queries_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    return row


@router.patch("/api/saved-queries/{slug}")
async def api_update_saved_query(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Update a saved query.  Only owner + admin may mutate.

    Args:
        request: The incoming request.
        slug: The slug of the row to update.
        body: Partial update payload — ``title``, ``description``,
            ``sql_text`` / ``sql``, ``is_shared``.  Any field not
            present is left unchanged.

    Returns:
        The updated row as a dict.

    Raises:
        CatalogNotFoundError: If the row is missing or the user
            is not the owner / admin.  (We do not differentiate
            so unauthorised clients cannot probe for existence.)
        ValidationError: If a non-``None`` title / sql is empty.
    """  # noqa: DOC502,DOC503 — raised by saved_queries.update_by_slug
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = get_user(request)
    payload = body or {}
    previous = await asyncio.to_thread(
        saved_queries_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    row = await asyncio.to_thread(
        saved_queries_service.update_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        description=payload.get("description")
        if isinstance(payload.get("description"), str)
        else None,
        sql_text=payload.get("sql_text")
        if isinstance(payload.get("sql_text"), str)
        else (payload.get("sql") if isinstance(payload.get("sql"), str) else None),
        is_shared=bool(payload.get("is_shared")) if "is_shared" in payload else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")

    action = "query.updated"
    if previous is not None and previous["is_shared"] != row["is_shared"]:
        action = "query.shared" if row["is_shared"] else "query.unshared"
    await audit(request, action, f"saved_query:{slug}", {"title": row["title"]})
    return row


@router.delete("/api/saved-queries/{slug}", status_code=204)
async def api_delete_saved_query(request: Request, slug: str) -> Response:
    """Delete a saved query.  Only owner + admin may delete.

    Args:
        request: The incoming request.
        slug: The slug of the row to delete.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: If the row is missing or the user
            is not owner / admin.
    """  # noqa: DOC502 — raised via service return value check
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = get_user(request)
    ok = await asyncio.to_thread(
        saved_queries_service.delete_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    if not ok:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    await audit(request, "query.deleted", f"saved_query:{slug}", None)
    return Response(status_code=204)
