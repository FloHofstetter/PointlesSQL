"""Notebook workspace HTTP routes (read-only post-pivot).

Phase 12.12.2 trimmed this module to the supervision-only surface:
the workspace HTML page plus the two read endpoints the page and the
jobs-create-modal lean on
(``GET /api/notebooks/tree``, ``GET /api/notebooks/inspect``).

Everything else — the browser editor shell
(``GET /notebook/editor``), the load / save / cell-run endpoints
(``GET`` / ``POST /api/notebook/doc`` and
``GET /api/notebook/cell-runs``), and the workspace CRUD
(``POST /api/notebooks/upload``, ``POST /api/notebooks/create``,
``PATCH /api/notebooks/rename``, ``DELETE /api/notebooks``) — was
removed in the agent-first pivot: humans no longer author notebooks
in the UI, agents drop ``.py`` jupytext-Percent files into
``notebooks/`` and the scheduler executes them. Human surface is
``/runs`` (supervision) + this page (read-only discovery + "schedule
this for Papermill" affordance).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import require_admin
from pointlessql.services import notebook_workspace as notebook_workspace_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.settings import Settings

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
        settings.jupyter.notebooks_dir.resolve(), path,
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
        :func:`pointlessql.services.notebook_workspace.list_workspace_tree`
        for the shape of each node.
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    return notebook_workspace_service.list_workspace_tree(settings.jupyter.notebooks_dir.resolve())


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
