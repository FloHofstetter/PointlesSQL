"""Admin CRUD for glossary terms + their column bindings.

Tenant-admin-gated JSON endpoints plus one HTML cockpit page,
mirroring the domains admin surface:

* ``GET  /admin/glossary`` — HTML list + create form + per-row
  binding drill-down.
* ``GET  /api/admin/glossary`` — list terms in the active workspace.
* ``POST /api/admin/glossary`` — create a term.
* ``DELETE /api/admin/glossary/{id}`` — delete (CASCADEs bindings).
* ``GET  /api/admin/glossary/{id}/bindings`` — list column bindings.
* ``POST /api/admin/glossary/{id}/bindings`` — bind a UC column.
* ``DELETE /api/admin/glossary/{id}/bindings/{binding_id}`` — unbind.

Every mutation logs to :class:`AuditLog` with the ``glossary.*``
action prefix.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import GlossaryTerm, GlossaryTermColumn
from pointlessql.services import glossary as glossary_service

router = APIRouter(tags=["admin-glossary"])


def _serialize_term(row: GlossaryTerm) -> dict[str, Any]:
    """Project a :class:`GlossaryTerm` ORM row to a JSON-safe dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "slug": row.slug,
        "term": row.term,
        "definition": row.definition,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_binding(row: GlossaryTermColumn) -> dict[str, Any]:
    """Project a :class:`GlossaryTermColumn` row to a JSON-safe dict."""
    return {
        "id": row.id,
        "glossary_term_id": row.glossary_term_id,
        "catalog": row.catalog,
        "schema": row.schema_name,
        "table": row.table_name,
        "column": row.column_name,
        "ref": f"{row.catalog}.{row.schema_name}.{row.table_name}.{row.column_name}",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_term(factory: Any, workspace_id: int, term_id: int) -> GlossaryTerm:
    """Return the workspace's term or raise :class:`CatalogNotFoundError`."""
    with factory() as session:
        row = session.get(GlossaryTerm, term_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"glossary term id={term_id} not found")
        session.expunge(row)
    return row


@router.get("/api/admin/glossary")
async def api_admin_list_terms(request: Request) -> dict[str, Any]:
    """List the active workspace's glossary terms."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = glossary_service.list_terms(factory, workspace_id=workspace_id)
    return {"terms": [_serialize_term(row) for row in rows]}


@router.post("/api/admin/glossary")
async def api_admin_create_term(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a glossary term.

    Args:
        request: Incoming FastAPI request.
        body: ``{"slug": str, "term": str, "definition"?: str}``.

    Returns:
        The serialized term row.

    Raises:
        ValidationError: On malformed slug / term or a slug already
            taken in the workspace.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    slug_raw = body.get("slug")
    term_raw = body.get("term")
    if not isinstance(slug_raw, str) or not slug_raw.strip():
        raise ValidationError("slug must be a non-empty string")
    if not isinstance(term_raw, str) or not term_raw.strip():
        raise ValidationError("term must be a non-empty string")
    definition = body.get("definition")
    user = get_user(request)
    creator_id = int(user["id"]) if user["id"] > 0 else None
    try:
        row = glossary_service.create_term(
            factory,
            workspace_id=workspace_id,
            slug=slug_raw,
            term=term_raw,
            definition=definition if isinstance(definition, str) else None,
            creator_user_id=creator_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "glossary.created",
        f"glossary:{row.slug}",
        {"id": row.id, "slug": row.slug, "term": row.term},
    )
    return _serialize_term(row)


@router.delete("/api/admin/glossary/{term_id}")
async def api_admin_delete_term(request: Request, term_id: int) -> dict[str, Any]:
    """Delete a glossary term (and, via CASCADE, its bindings)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    term = _ensure_term(factory, workspace_id, term_id)
    deleted = glossary_service.delete_term(factory, term_id=term_id)
    if deleted:
        await audit(
            request,
            "glossary.deleted",
            f"glossary:{term.slug}",
            {"id": term_id, "slug": term.slug},
        )
    return {"deleted": deleted}


@router.get("/api/admin/glossary/{term_id}/bindings")
async def api_admin_list_bindings(request: Request, term_id: int) -> dict[str, Any]:
    """Return every column binding for a term."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_term(factory, workspace_id, term_id)
    rows = glossary_service.list_bindings(factory, term_id=term_id)
    return {"term_id": term_id, "bindings": [_serialize_binding(r) for r in rows]}


@router.post("/api/admin/glossary/{term_id}/bindings")
async def api_admin_bind_column(
    request: Request,
    term_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Bind a term to one UC column.

    Args:
        request: Incoming FastAPI request.
        term_id: ``GlossaryTerm.id``.
        body: ``{"catalog": str, "schema": str, "table": str,
            "column": str}``.

    Returns:
        The serialized binding row.

    Raises:
        ValidationError: When a ref segment is missing.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_term(factory, workspace_id, term_id)
    try:
        row = glossary_service.bind_column(
            factory,
            term_id=term_id,
            catalog=str(body.get("catalog", "")),
            schema=str(body.get("schema", "")),
            table=str(body.get("table", "")),
            column=str(body.get("column", "")),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "glossary.column_bound",
        f"glossary:{term_id}",
        {"binding_id": row.id, "ref": _serialize_binding(row)["ref"]},
    )
    return _serialize_binding(row)


@router.delete("/api/admin/glossary/{term_id}/bindings/{binding_id}")
async def api_admin_unbind_column(
    request: Request, term_id: int, binding_id: int
) -> dict[str, Any]:
    """Remove a column binding from a term."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_term(factory, workspace_id, term_id)
    deleted = glossary_service.unbind_column(factory, binding_id=binding_id)
    if deleted:
        await audit(
            request,
            "glossary.column_unbound",
            f"glossary:{term_id}",
            {"binding_id": binding_id},
        )
    return {"deleted": deleted}


@router.get("/admin/glossary", response_class=HTMLResponse)
async def admin_glossary_page(request: Request):
    """Render the admin glossary cockpit (list + create + bindings)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    terms = glossary_service.list_terms(factory, workspace_id=workspace_id)
    binding_counts: dict[int, int] = {
        row.id: len(glossary_service.list_bindings(factory, term_id=row.id)) for row in terms
    }
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_glossary.html",
        {
            "active_page": "admin",
            "terms": terms,
            "binding_counts": binding_counts,
        },
    )
