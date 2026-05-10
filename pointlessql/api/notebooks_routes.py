"""Notebook workspace HTTP routes — discovery, CRUD, page render.

Hosts the workspace HTML page, the two read endpoints the page and
the jobs-create-modal lean on (``GET /api/notebooks/tree``,
``GET /api/notebooks/inspect``), and the create / rename / delete
mutations the Phase-66 browser editor uses to manage ``.py`` files.

The execute / load / save endpoints belong to sibling modules:

* ``GET  /api/notebooks/load`` — Sprint 66.1 (frontend skeleton).
* ``POST /api/notebooks/save`` — Sprint 66.2 (save round-trip).
* ``WS   /ws/notebook/kernel`` — Sprint 66.0 (this phase, separate
  module ``notebook_kernel_ws.py``).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import require_admin
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.notebook import _workspace as notebook_workspace_service
from pointlessql.services.notebook import outputs as notebook_outputs_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


@router.get("/api/notebooks/inspect")
async def api_inspect_notebook(request: Request, path: str) -> list[dict[str, Any]]:
    """Return a notebook's declared Papermill parameters.

    Introspects the ``parameters``-tagged cell via
    :func:`papermill.inspect_notebook` and returns one entry per
    declared parameter. The create-job modal uses this to render a
    typed form instead of the raw JSON textarea.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path, resolved under
            :attr:`Settings.notebooks_dir`. Must not escape the
            directory — uses the same validator as the executor.

    Returns:
        A list of ``{"name", "default", "inferred_type", "help"}``
        dicts. ``default`` is the literal default string Papermill
        extracts (the client coerces it per ``inferred_type``).
    """
    import papermill  # type: ignore[import-untyped]

    require_admin(request)
    settings: Settings = request.app.state.settings
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        path,
    )
    raw = papermill.inspect_notebook(str(resolved))
    out: list[dict[str, Any]] = []
    for name, meta in raw.items():
        meta_dict: dict[str, Any] = meta
        out.append(
            {
                "name": name,
                "default": meta_dict.get("default"),
                "inferred_type": meta_dict.get("inferred_type_name") or "str",
                "help": meta_dict.get("help", ""),
            },
        )
    return out


@router.get("/api/notebooks/tree")
async def api_notebooks_tree(request: Request) -> list[dict[str, Any]]:
    """Return a nested listing of the notebooks workspace directory.

    Admin-only, matching the inspect route. Each notebook leaf carries
    a ``parameters_tagged`` flag so the workspace UI can hint which
    files will render a typed form in the create-job modal.

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        A list of directory and notebook nodes. See
        :func:`pointlessql.services.notebook._workspace.list_workspace_tree`
        for the shape of each node.
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    return notebook_workspace_service.list_workspace_tree(settings.jupyter.notebooks_dir.resolve())


@router.post("/api/notebooks/create", status_code=201)
async def api_create_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Create an empty ``.py`` notebook under the workspace root.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with key ``path`` (required, relative path
            ending in ``.py``).

    Returns:
        JSON ``{"path": "<relative>"}`` on success; 422 with the
        :class:`ValidationError` envelope on bad input.

    Raises:
        ValidationError: When ``body.path`` is missing / non-string,
            escapes the workspace root, has the wrong suffix, or
            already exists on disk.
    """
    require_admin(request)
    raw_path = body.get("path") if isinstance(body, dict) else None
    if not isinstance(raw_path, str):
        raise ValidationError("body.path must be a string")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    resolved = notebook_workspace_service.create_empty_notebook(
        notebooks_dir, raw_path
    )
    relative = str(resolved.relative_to(notebooks_dir))
    logger.info(
        "created notebook %s (%s)",
        relative,
        request.state.user.get("email") if hasattr(request.state, "user") else "?",
    )
    return JSONResponse({"path": relative}, status_code=201)


@router.post("/api/notebooks/rename")
async def api_rename_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Move a notebook to a new path under the workspace root.

    Re-keys persisted ``notebook_outputs`` rows so the editor at the
    new path replays the prior session's outputs verbatim.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with keys ``from_path`` and ``to_path``.

    Returns:
        JSON ``{"from_path": ..., "to_path": ...}`` on success.

    Raises:
        ValidationError: On any of the shared resolver guards
            (traversal, suffix, missing source, existing target).
    """
    require_admin(request)
    from_path = body.get("from_path") if isinstance(body, dict) else None
    to_path = body.get("to_path") if isinstance(body, dict) else None
    if not isinstance(from_path, str) or not isinstance(to_path, str):
        raise ValidationError("body.from_path and body.to_path must be strings")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    notebook_workspace_service.rename_notebook(notebooks_dir, from_path, to_path)
    notebook_outputs_service.rename_path(
        request.app.state.session_factory,
        from_path,
        to_path,
    )
    logger.info("renamed notebook %s -> %s", from_path, to_path)
    return JSONResponse({"from_path": from_path, "to_path": to_path})


@router.delete("/api/notebooks/delete")
async def api_delete_notebook(
    request: Request,
    path: str = Query(..., min_length=1),
    confirm: bool = Query(False),
) -> JSONResponse:
    """Delete a notebook + cascade its persisted outputs.

    The confirm-flag keeps a stray ``DELETE /api/notebooks/delete``
    from a misconfigured client from wiping a file silently — the
    browser editor flips it to ``true`` after the user OKs the
    confirm modal.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative path of the notebook to delete.
        confirm: Must be ``true`` to actually delete; ``false`` is
            a 400 with a clear envelope.

    Returns:
        JSON ``{"path": ...}`` on success.

    Raises:
        HTTPException: 400 when ``confirm`` is not ``true`` — the
            browser editor sets it after the confirm-modal pick;
            curl callers must opt in explicitly.
    """
    require_admin(request)
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    notebook_workspace_service.delete_notebook(notebooks_dir, path)
    notebook_outputs_service.clear_path(request.app.state.session_factory, path)
    logger.info("deleted notebook %s", path)
    return JSONResponse({"path": path})


@router.get("/notebooks/workspace", response_class=HTMLResponse)
async def notebooks_workspace_page(request: Request) -> HTMLResponse:
    """Render the workspace file browser (admin-only, read-only).

    Post-pivot: the page lists ``.py`` / ``.ipynb`` notebooks the
    scheduler can pick up and offers a *Schedule…* button per leaf
    that navigates to
    ``/jobs?prefill_kind=papermill&prefill_notebook_path=<path>``;
    authoring happens outside PointlesSQL (agents drop files onto the
    notebooks directory).

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        The rendered ``pages/notebooks_workspace.html`` template.
    """
    require_admin(request)
    return _templates(request).TemplateResponse(
        request,
        "pages/notebooks_workspace.html",
        {
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
