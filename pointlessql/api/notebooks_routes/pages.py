"""HTML page renders for the notebook editor + workspace browser."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.api.notebooks_routes._shared import (
    get_or_create_notebook_uuid,
    templates,
)
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook.cell_tags import CURATED_CELL_TAGS

router = APIRouter(tags=["notebooks"])


@router.get("/notebooks/edit/{path:path}", response_class=HTMLResponse)
async def notebook_editor_page(request: Request, path: str) -> HTMLResponse:
    """Render the browser notebook editor for a specific ``.py`` file.

    The path is validated against the workspace root before render so
    a bad path 422s before a stale editor frame paints.  The editor
    boots itself from ``GET /api/notebooks/load`` after Alpine mounts.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative notebook path, captured by the
            ``{path:path}`` converter (slashes preserved).

    Returns:
        The rendered ``pages/notebook_editor.html`` template.

    Raises:
        ValidationError: When the path is missing / outside the
            workspace / wrong suffix / does not exist.  Surfaces
            via :func:`resolve_py_notebook_path`.
    """  # noqa: DOC502
    require_user(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    notebook_uuid = get_or_create_notebook_uuid(request, relative)
    return templates(request).TemplateResponse(
        request,
        "pages/notebook_editor.html",
        {
            "notebook_path": relative,
            "notebook_uuid": notebook_uuid,
            "curated_cell_tags": list(CURATED_CELL_TAGS),
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get(
    "/notebooks/uuid/{notebook_uuid}", response_class=HTMLResponse
)
async def notebook_editor_by_uuid(
    request: Request, notebook_uuid: str
) -> HTMLResponse:
    """Render the editor for a notebook addressed by its UUID.

    Phase 77.6 — the UUID-routed alias lets the social-layer
    citations + audit-log links survive a path rename.  The
    backing data is identical to ``/notebooks/edit/{path}``; we
    just look up the file_path from the ``notebooks`` row and
    delegate to the same render path.

    Args:
        request: Incoming FastAPI request.
        notebook_uuid: 36-char UUID stored on ``notebooks.id``.

    Returns:
        The rendered ``pages/notebook_editor.html`` template.

    Raises:
        ValidationError: When the UUID does not resolve or the
            backing file is missing.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        nb = session.execute(
            select(Notebook).where(
                Notebook.id == notebook_uuid,
                Notebook.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if nb is None:
            raise ValidationError(f"notebook {notebook_uuid} not found")
        file_path = str(nb.file_path)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, file_path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return templates(request).TemplateResponse(
        request,
        "pages/notebook_editor.html",
        {
            "notebook_path": relative,
            "notebook_uuid": notebook_uuid,
            "curated_cell_tags": list(CURATED_CELL_TAGS),
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/notebooks/workspace", response_class=HTMLResponse)
async def notebooks_workspace_page(request: Request) -> HTMLResponse:
    """Render the workspace file browser (member-accessible).

    Post-pivot: the page lists ``.py`` / ``.ipynb`` notebooks the
    scheduler can pick up and offers a *Schedule…* button per leaf
    that navigates to
    ``/jobs?prefill_kind=papermill&prefill_notebook_path=<path>``;
    authoring happens outside PointlesSQL (agents drop files onto the
    notebooks directory).

    Args:
        request: Incoming FastAPI request; any authenticated user.

    Returns:
        The rendered ``pages/notebooks_workspace.html`` template.
    """
    require_user(request)
    return templates(request).TemplateResponse(
        request,
        "pages/notebooks_workspace.html",
        {
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
