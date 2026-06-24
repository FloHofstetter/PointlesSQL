"""Glossary browse surface — read-only pages + JSON for all users.

Glossary terms are *managed* by admins (see
:mod:`pointlessql.api.admin.glossary`) but *browsable* by every
authenticated user, mirroring the domains split:

* ``GET /glossary`` — index with a card per term.
* ``GET /glossary/{slug}`` — detail page (definition + bound columns).
* ``GET /api/glossary`` — JSON list used by the browse page and the
  ``pql_list_glossary`` agent tool.
* ``GET /api/glossary/{slug}`` — JSON detail (term + column bindings).

The HTML pages redirect anonymous visitors to ``/auth/login?next=...``;
the auth middleware gates everything outside ``PUBLIC_PREFIXES`` so no
allowlist entry is needed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_user,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.services import glossary as glossary_service

router = APIRouter(tags=["glossary"])


def _serialise_term(row: Any) -> dict[str, Any]:
    """Render a :class:`GlossaryTerm` row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "slug": row.slug,
        "term": row.term,
        "definition": row.definition,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialise_binding(row: Any) -> dict[str, Any]:
    """Render a :class:`GlossaryTermColumn` row as a JSON-friendly dict."""
    return {
        "catalog": row.catalog,
        "schema": row.schema_name,
        "table": row.table_name,
        "column": row.column_name,
        "ref": f"{row.catalog}.{row.schema_name}.{row.table_name}.{row.column_name}",
    }


@router.get("/api/glossary")
async def api_list_terms(request: Request) -> dict[str, Any]:
    """List the active workspace's glossary terms with binding counts."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = glossary_service.list_terms(factory, workspace_id=workspace_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = _serialise_term(row)
        payload["binding_count"] = len(glossary_service.list_bindings(factory, term_id=row.id))
        out.append(payload)
    return {"terms": out}


@router.get("/api/glossary/{slug}")
async def api_term_detail(request: Request, slug: str) -> dict[str, Any]:
    """Return one glossary term with its column bindings.

    Open to any signed-in user: ``require_user`` answers 403 for
    anonymous callers.

    Args:
        request: Incoming FastAPI request.
        slug: Term slug from the URL.

    Returns:
        The serialized term plus its column bindings.

    Raises:
        ResourceNotFoundError: When no term with *slug* exists in the
            active workspace — rendered as 404.
    """
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    term = glossary_service.get_term_by_slug(factory, workspace_id=workspace_id, slug=slug)
    if term is None:
        raise ResourceNotFoundError(f"glossary term {slug!r} not found")
    bindings = glossary_service.list_bindings(factory, term_id=term.id)
    payload = _serialise_term(term)
    payload["bindings"] = [_serialise_binding(b) for b in bindings]
    return payload


@router.get("/glossary", response_class=HTMLResponse, response_model=None)
async def glossary_index_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the workspace-wide glossary index page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/glossary", status_code=303)
    return get_templates(request).TemplateResponse(
        request,
        "pages/glossary.html",
        {"active_page": "glossary", "is_admin": user["is_admin"]},
    )


@router.get("/glossary/{slug}", response_class=HTMLResponse, response_model=None)
async def glossary_detail_page(request: Request, slug: str) -> HTMLResponse | RedirectResponse:
    """Render one glossary term's detail page (definition + bindings).

    Anonymous visitors are redirected (303) to the login page with a
    ``next`` deep-link instead of being rendered the page; signed-in
    users get the rendered detail page.

    Args:
        request: Incoming FastAPI request.
        slug: Term slug from the URL.

    Returns:
        The rendered detail page, or a 303 redirect to login for
        anonymous visitors.

    Raises:
        ResourceNotFoundError: When no term with *slug* exists in the
            active workspace — rendered as 404.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url=f"/auth/login?next=/glossary/{slug}", status_code=303)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    term = glossary_service.get_term_by_slug(factory, workspace_id=workspace_id, slug=slug)
    if term is None:
        raise ResourceNotFoundError(f"glossary term {slug!r} not found")
    return get_templates(request).TemplateResponse(
        request,
        "pages/glossary_detail.html",
        {
            "active_page": "glossary",
            "is_admin": user["is_admin"],
            "term_slug": term.slug,
            "term_name": term.term,
        },
    )
