"""Notebook editor + workspace HTTP routes.

Sprint 88a split out of ``api/main.py``.  Owns the HTTP-only half of
the notebook surface:

* The editor page + bundle endpoints
  (``GET /notebook/editor``, ``GET /api/notebook/doc``,
  ``GET /api/notebook/cell-runs``, ``POST /api/notebook/doc``).
* The workspace CRUD + tree
  (``GET /api/notebooks/tree``, ``GET /api/notebooks/inspect``,
  ``POST /api/notebooks/upload``, ``POST /api/notebooks/create``,
  ``PATCH /api/notebooks/rename``, ``DELETE /api/notebooks``).
* The workspace HTML page (``GET /notebooks/workspace``).

The two WebSocket endpoints (``/ws/notebook/kernel`` +
``/ws/notebook/lsp``) and the ``_resolve_sql_approved_tables``
helper they share live in ``api/notebook_kernel_ws.py`` since
Sprint 88b — they have a separate, ZMQ-coupled lifecycle that
deserves its own module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import ValidationError
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import notebook_outputs as notebook_outputs_service
from pointlessql.services import notebook_workspace as notebook_workspace_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


async def build_notebook_doc_bundle(
    request: Request, path: str,
) -> dict[str, Any]:
    """Assemble the ``{cells, dirty, outputs}`` bundle for a notebook.

    Shared by the HTML editor route (which embeds the bundle into the
    page template for first-paint hydration) and the Sprint-68 JSON
    route (which hands the same bundle to the multi-tab editor shell
    when it lazy-loads a second tab without a page reload).

    Args:
        request: Incoming FastAPI request; carries app-state settings
            and session factory.
        path: Relative ``.py`` notebook path under the notebooks dir.

    Returns:
        A dict with ``cells`` (list of ``{id, content_hash, cell_type,
        source, result_var}``), ``dirty`` (bool), and ``outputs`` (list
        of persisted outputs replayed from ``notebook_outputs``).
        Sprint 96: ``id`` is a transient per-load ordinal label
        (``cell-0``, ``cell-1``, …) used only as the client's
        ``x-for :key`` for DOM reconciliation; ``content_hash`` is the
        stable identity the client sends in every WS frame and uses
        to look up persisted outputs.
    """
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    resolved = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=False,
    )
    if resolved.is_file():
        document = notebook_doc_service.load_document(resolved, path)
        bundle: dict[str, Any] = {
            "cells": [
                {
                    "id": cell.id,
                    "content_hash": cell.content_hash,
                    "cell_type": cell.cell_type,
                    "source": cell.source,
                    # Sprint 71 BUG-71-02 fix: round-trip the SQL
                    # cell's optional ``result_var`` through the
                    # bundle so the editor's affordances re-mount
                    # with the user-defined name pre-populated.
                    "result_var": cell.result_var,
                }
                for cell in document.cells
            ],
            "dirty": document.dirty,
        }
    else:
        empty_source = ""
        bundle = {
            "cells": [
                {
                    "id": "cell-0",
                    "content_hash": notebook_doc_service.compute_content_hash(
                        empty_source,
                    ),
                    "cell_type": "code",
                    "source": empty_source,
                    "result_var": None,
                },
            ],
            "dirty": True,
        }
    bundle["outputs"] = await asyncio.to_thread(
        notebook_outputs_service.load_outputs_for_path,
        request.app.state.session_factory,
        path,
    )
    return bundle


@router.get("/notebook/editor", response_class=HTMLResponse)
async def notebook_editor_page(request: Request, path: str) -> HTMLResponse:
    """Render the native Phase-12.6 notebook editor (preview).

    The editor opens the ``.py`` (jupytext Percent format) notebook at
    ``path``, relative to the notebooks directory. If the file does
    not exist yet the page renders with a single empty code cell and
    first save materialises the file on disk — mirrors how VSCode's
    Python Interactive window treats a fresh buffer.

    Args:
        request: Incoming FastAPI request.
        path: Relative path under :attr:`Settings.notebooks_dir`.
            Must end in ``.py`` and must not escape the notebooks
            directory.

    Returns:
        Rendered HTML carrying the initial document as a JSON blob
        the Alpine component consumes synchronously on mount.
    """
    initial = await build_notebook_doc_bundle(request, path)
    return _templates(request).TemplateResponse(
        request,
        "pages/notebook_editor.html",
        {
            "notebook_path": path,
            "initial_document": initial,
            "active_page": "notebook_editor",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/notebook/doc")
async def api_load_notebook_doc(
    request: Request, path: str,
) -> dict[str, Any]:
    """Return the notebook bundle as JSON for the multi-tab editor.

    Sprint-68 companion of the HTML editor route: when the user opens a
    second notebook in a new tab without a full page reload, the shell
    fetches this endpoint to hydrate the tab's Monaco model + replay
    its persisted outputs. Same shape as
    :func:`notebook_editor_page`'s ``initial_document`` — a single
    helper produces both — so the first-paint and lazy-load code paths
    can never drift.

    Args:
        request: Incoming FastAPI request.
        path: Relative ``.py`` notebook path under the notebooks dir.

    Returns:
        ``{"cells": [...], "dirty": bool, "outputs": [...]}``.
    """
    return await build_notebook_doc_bundle(request, path)


@router.get("/api/notebook/cell-runs")
async def api_list_cell_run_sources(
    request: Request, path: str, content_hash: str, limit: int = 20,
) -> dict[str, Any]:
    """Return the last *limit* per-execute history rows for a cell.

    Sprint 73 — backs the per-cell run-history popover in the editor.
    Each row carries the source the kernel actually saw, the
    lifecycle status, and the start / finish timestamps; the popover
    renders a diff between consecutive ``source`` snapshots and
    offers a one-click re-run that sends the historical source
    straight to the kernel without touching the Monaco buffer.

    Sprint 96 renamed the ``cell_id`` query param to ``content_hash``
    in lock-step with the DB rename and the marker-grammar cleanup.

    Args:
        request: Incoming FastAPI request.
        path: Relative ``.py`` notebook path under the notebooks dir.
        content_hash: Cell identity (``sha256(source)[:16]``) to
            filter on.
        limit: Maximum number of rows to return (newest-first).

    Returns:
        ``{"runs": [{"id", "execution_count", "source", "started_at",
        "finished_at", "status", "kernel_session_id"}, ...]}``
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path, must_exist=False,
    )
    factory = request.app.state.session_factory
    runs = await asyncio.to_thread(
        notebook_outputs_service.list_cell_run_sources,
        factory,
        file_path=path,
        content_hash=content_hash,
        limit=max(1, min(limit, 100)),
    )
    return {"runs": runs}


@router.post("/api/notebook/doc")
async def api_save_notebook_doc(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, str]:
    """Persist a notebook document from the Sprint-58 editor to disk.

    The request body is ``{"path": str, "cells": [{"cell_type",
    "source", "result_var?"}, …]}``. Cells are written in jupytext
    Percent format via :func:`notebook_doc.save_document`; a missing
    parent directory is a :class:`ValidationError` so the editor never
    silently creates arbitrary nested folders.

    Sprint 96 dropped the required ``id`` field on each cell. The
    Percent-format grammar carries no per-cell UUID anymore, so the
    server accepts cells with just ``cell_type`` + ``source`` (plus
    the SQL-only ``result_var``) and computes the ``content_hash``
    identity itself. Clients that still send a transient ``id`` label
    have it ignored.

    Args:
        request: Incoming FastAPI request. The CSRF middleware already
            checks the ``X-CSRF-Token`` header before the handler runs.
        body: The parsed JSON payload.

    Returns:
        ``{"path": str, "status": "saved"}``.

    Raises:
        ValidationError: On bad payload shape, traversal attempt, or
            non-existent parent directory.
    """
    settings: Settings = request.app.state.settings
    path = body.get("path")
    raw_cells = body.get("cells")
    if not isinstance(path, str) or not isinstance(raw_cells, list):
        raise ValidationError("payload must carry 'path': str and 'cells': list")
    cells: list[notebook_doc_service.NotebookCell] = []
    for idx, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise ValidationError(f"cell {idx} must be an object")
        cell_type = raw.get("cell_type")
        source = raw.get("source")
        # Sprint 71 BUG-71-02 fix: accept ``sql`` alongside ``code`` /
        # ``markdown`` and read the optional ``result_var`` field so
        # the post-jupytext rewrite can put the segment back on disk.
        result_var = raw.get("result_var")
        if cell_type not in ("code", "markdown", "sql"):
            raise ValidationError(f"cell {idx} has unsupported cell_type {cell_type!r}")
        if not isinstance(source, str):
            raise ValidationError(f"cell {idx} 'source' must be a string")
        if result_var is not None and not isinstance(result_var, str):
            raise ValidationError(
                f"cell {idx} 'result_var' must be a string or null",
            )
        cells.append(
            notebook_doc_service.NotebookCell(
                id=f"cell-{idx}",
                content_hash=notebook_doc_service.compute_content_hash(source),
                cell_type=cell_type,
                source=source,
                result_var=result_var if cell_type == "sql" else None,
            ),
        )
    resolved = notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path, must_exist=False,
    )
    notebook_doc_service.save_document(resolved, cells)
    await audit(request, "notebook.saved", f"notebook:{path}", f"cells={len(cells)}")
    return {"path": path, "status": "saved"}


@router.get("/api/notebooks/inspect")
async def api_inspect_notebook(request: Request, path: str) -> list[dict[str, Any]]:
    """Return a notebook's declared Papermill parameters.

    Introspects the ``parameters``-tagged cell via
    :func:`papermill.inspect_notebook` and returns one entry per
    declared parameter. The create-job modal uses this to render a
    typed form instead of the raw JSON textarea introduced in
    Sprint 24.

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

    Admin-only, matching the inspect + upload routes in this family.
    Each notebook leaf carries a ``parameters_tagged`` flag so the
    workspace UI can hint which files will render a typed form in
    the create-job modal.

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


@router.post("/api/notebooks/upload")
async def api_upload_notebook(
    request: Request,
    file: UploadFile = File(...),
    target_path: str = Form(...),
    overwrite: bool = Form(False),
) -> dict[str, str]:
    """Upload an ``.ipynb`` file into the notebooks workspace.

    Admin-only. The ``target_path`` is resolved under
    :attr:`Settings.notebooks_dir` with the same traversal guard the
    executor uses (via
    :func:`pointlessql.services.notebook_workspace.resolve_upload_target`).
    The upload payload must be a well-formed JSON notebook; the body
    is parsed before the file hits disk so a corrupt upload never
    leaves a half-written file in the workspace. Writes are atomic
    via a ``.tmp`` sidecar + :func:`os.replace`.

    Args:
        request: Incoming FastAPI request; admin-only.
        file: The multipart upload. ``file.filename`` must end in
            ``.ipynb``.
        target_path: Relative path under the notebooks directory
            where the upload should land.
        overwrite: When ``True``, an existing file at ``target_path``
            is replaced. When ``False`` (the default), attempting to
            upload over an existing file raises
            :class:`~pointlessql.exceptions.ValidationError`.

    Returns:
        A dict with ``path`` (the relative path the file was written
        to) and ``status`` (``"created"`` or ``"overwritten"``).

    Raises:
        ValidationError: On any of the upload guards (bad filename,
            path traversal, malformed JSON body, existing file
            without ``overwrite=True``). ``AuthorizationError`` is
            raised out of ``require_admin`` for non-admin callers
            and surfaced as 403 by the centralized error handler.
    """
    import os

    require_admin(request)
    settings: Settings = request.app.state.settings

    filename = file.filename or ""
    if not filename.endswith(".ipynb"):
        raise ValidationError(f"uploaded file must have an .ipynb extension: {filename!r}")

    resolved = notebook_workspace_service.resolve_upload_target(
        settings.jupyter.notebooks_dir.resolve(), target_path,
    )

    raw = await file.read()
    try:
        json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"uploaded file is not valid JSON: {exc}") from exc

    existed = resolved.exists()
    if existed and not overwrite:
        raise ValidationError(
            f"file already exists at {target_path!r}; pass overwrite=true to replace",
        )

    tmp_path = resolved.with_suffix(resolved.suffix + ".tmp")
    tmp_path.write_bytes(raw)
    os.replace(tmp_path, resolved)

    await audit(
        request,
        action="notebook.upload",
        target=target_path,
        detail=f"overwrite={overwrite}",
    )
    logger.info(
        "notebook uploaded to %s (overwrite=%s, existed=%s)",
        target_path,
        overwrite,
        existed,
    )
    return {
        "path": target_path,
        "status": "overwritten" if existed else "created",
    }


@router.post("/api/notebooks/create")
async def api_create_notebook(
    request: Request, body: dict[str, Any] = Body(...),
) -> dict[str, str]:
    """Create an empty ``.py`` notebook in the workspace (admin-only).

    Sprint 67 sidebar "New…" action. Writes a zero-byte file at
    ``body["path"]`` — the editor's open handler at
    :func:`notebook_editor_page` already renders an empty cell and
    materialises cell markers on first save when it encounters a
    zero-byte file, so there is no template content to maintain here.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with a required ``path`` key naming the
            relative ``.py`` path to create.

    Returns:
        ``{"path": "...", "status": "created"}``.

    Raises:
        ValidationError: On traversal, wrong suffix, missing parent
            directory, or when a file already exists at ``path``.
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    raw = body.get("path")
    if not isinstance(raw, str):
        raise ValidationError("create request requires a 'path' string")
    notebook_workspace_service.create_empty_notebook(
        settings.jupyter.notebooks_dir.resolve(), raw,
    )
    await audit(request, action="notebook.create", target=raw)
    logger.info("notebook created at %s", raw)
    return {"path": raw, "status": "created"}


@router.patch("/api/notebooks/rename")
async def api_rename_notebook(
    request: Request, body: dict[str, Any] = Body(...),
) -> dict[str, str]:
    """Rename an existing notebook and re-key its replay cache.

    Sprint 67 sidebar rename action. The filesystem move goes through
    :func:`notebook_workspace.rename_notebook`; the replay cache in
    ``notebook_outputs`` + ``notebook_cell_runs`` is re-keyed by
    :func:`notebook_outputs.rename_path` so prior run artefacts
    survive the rename — a UX property a user expects when the only
    thing they changed was the file's name.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with required ``old_path`` and ``new_path``
            keys, both relative to the notebooks directory.

    Returns:
        ``{"old_path": "...", "new_path": "...", "status": "renamed"}``.

    Raises:
        ValidationError: On traversal / suffix violations, when the
            source is missing, or when the destination already
            exists.
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    old_raw = body.get("old_path")
    new_raw = body.get("new_path")
    if not isinstance(old_raw, str) or not isinstance(new_raw, str):
        raise ValidationError("rename request requires 'old_path' and 'new_path' strings")
    notebook_workspace_service.rename_notebook(
        settings.jupyter.notebooks_dir.resolve(), old_raw, new_raw,
    )
    await asyncio.to_thread(
        notebook_outputs_service.rename_path,
        request.app.state.session_factory,
        old_raw,
        new_raw,
    )
    await audit(
        request,
        action="notebook.rename",
        target=old_raw,
        detail=f"new_path={new_raw}",
    )
    logger.info("notebook renamed from %s to %s", old_raw, new_raw)
    return {"old_path": old_raw, "new_path": new_raw, "status": "renamed"}


@router.delete("/api/notebooks")
async def api_delete_notebook(request: Request, path: str) -> dict[str, str]:
    """Delete a notebook and cascade its replay cache (admin-only).

    Sprint 67 sidebar delete action. ``path`` is taken as a query
    parameter rather than a ``{path:path}`` URL segment to sidestep
    the regex-vs-slash ambiguity that nested notebook paths
    (``sub/dir/foo.py``) introduce. The filesystem ``unlink`` happens
    first; the replay-cache cascade via :func:`clear_path` happens
    after and can tolerate "no rows matched" for a notebook that was
    never executed.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path to delete.

    Returns:
        ``{"path": "...", "status": "deleted"}``.  The ``ValidationError``
        contract of :func:`notebook_workspace.delete_notebook` applies
        — traversal / suffix violations and already-missing files
        raise.
    """
    require_admin(request)
    settings: Settings = request.app.state.settings
    notebook_workspace_service.delete_notebook(
        settings.jupyter.notebooks_dir.resolve(), path,
    )
    await asyncio.to_thread(
        notebook_outputs_service.clear_path,
        request.app.state.session_factory,
        path,
    )
    await audit(request, action="notebook.delete", target=path)
    logger.info("notebook deleted at %s", path)
    return {"path": path, "status": "deleted"}


@router.get("/notebooks/workspace", response_class=HTMLResponse)
async def notebooks_workspace_page(request: Request) -> HTMLResponse:
    """Render the Sprint 27 workspace file browser (admin-only).

    The page pairs a notebook-tree sidebar (served by
    ``/api/notebooks/tree``) with an upload card. Tree-leaf
    *Schedule…* buttons navigate to
    ``/jobs?prefill_kind=papermill&prefill_notebook_path=<path>``;
    the create-job modal reads those query params on load and
    pre-fills itself.

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
