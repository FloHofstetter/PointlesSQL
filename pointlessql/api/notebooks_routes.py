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
from pointlessql.services import output_rendering as notebook_render_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.notebook import _doc as notebook_doc_service
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
    declared parameter. The create-job modal and the in-editor
    Schedule + Run-Once modals (Phase 67) use this to render a typed
    form instead of the raw JSON textarea.

    Papermill's introspector only accepts ``.ipynb`` JSON; ``.py``
    jupytext-Percent notebooks (PointlesSQL's canonical on-disk
    format since Phase 12.10) get a transient conversion through a
    :class:`tempfile.NamedTemporaryFile` before the call so the
    caller never sees the difference.

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
    import tempfile

    import jupytext  # type: ignore[import-untyped]
    import nbformat  # type: ignore[import-untyped]
    import papermill  # type: ignore[import-untyped]

    require_admin(request)
    settings: Settings = request.app.state.settings
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        path,
    )
    if resolved.suffix == ".py":
        notebook = jupytext.read(resolved, fmt="py:percent")
        # Papermill's introspector reads the kernelspec to render
        # Jinja default-rewrites. Our jupytext-converted .py never
        # carries one (kernel selection is run-time via the WS layer),
        # so we stamp the canonical ``python3`` kernel here. Same
        # name :func:`_run_papermill_blocking` passes to execute.
        notebook.metadata.setdefault("kernelspec", {})
        notebook.metadata["kernelspec"].setdefault("name", "python3")
        notebook.metadata["kernelspec"].setdefault("display_name", "Python 3")
        notebook.metadata["kernelspec"].setdefault("language", "python")
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as fh:
            converted_path = fh.name
        try:
            nbformat.write(notebook, converted_path)
            raw = papermill.inspect_notebook(converted_path)
        finally:
            from pathlib import Path as _Path

            try:
                _Path(converted_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("inspect: failed to delete temp %s", converted_path)
    else:
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


@router.get("/api/notebooks/jobs")
async def api_notebook_jobs(
    request: Request,
    path: str,
    limit: int = 10,
) -> dict[str, Any]:
    """List scheduled jobs + recent runs for one notebook.

    Powers the Phase 67.4 in-editor side-panel that surfaces
    "what runs does this notebook have?" without making the user
    navigate to ``/jobs`` and filter manually. Joins
    :class:`NotebookJobLink` → :class:`Job` for the scheduled set,
    then pulls the most-recent :class:`JobRun` rows across all those
    jobs.

    Args:
        request: Incoming FastAPI request; admin-only (matches the
            other notebook routes — non-admins do not schedule jobs).
        path: Relative notebook path the editor is open on.
        limit: Optional cap on the recent-runs list, clamped to
            ``[1, 50]``. Default 10 mirrors the panel design.

    Returns:
        A JSON dict ``{scheduled_jobs: [...], recent_runs: [...]}``.
        Each scheduled entry carries job_id + name + cron + paused
        flag + last_run_at/status; recent_runs are flat
        :class:`JobRun` summaries newest-first.

    Raises:
        ValidationError: When ``path`` is missing or non-string.
    """  # noqa: DOC502
    from sqlalchemy import select as _select

    from pointlessql.api.jobs_routes import serialize_job as _serialize_job
    from pointlessql.api.jobs_routes import serialize_run as _serialize_run
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel
    from pointlessql.models import NotebookJobLink as _NJL

    require_admin(request)
    if not isinstance(path, str) or not path:
        raise ValidationError("`path` is required")
    limit = max(1, min(int(limit), 50))
    factory = request.app.state.session_factory
    with factory() as session:
        link_stmt = _select(_NJL).where(_NJL.notebook_path == path)
        link_rows = list(session.scalars(link_stmt).all())
        job_ids = [r.job_id for r in link_rows]
        scheduled: list[dict[str, Any]] = []
        recent: list[dict[str, Any]] = []
        if job_ids:
            jobs_stmt = _select(JobModel).where(JobModel.id.in_(job_ids))
            job_rows = list(session.scalars(jobs_stmt).all())
            for j in job_rows:
                session.expunge(j)
            # Last-run lookup per job (one round-trip via subquery).
            from pointlessql.api.jobs_routes import latest_run_per_job as _latest

            last_runs_map = _latest(session, [int(j.id) for j in job_rows])
            for j in job_rows:
                scheduled.append(_serialize_job(j, last_runs_map.get(int(j.id))))

            runs_stmt = (
                _select(JobRunModel)
                .where(JobRunModel.job_id.in_(job_ids))
                .order_by(JobRunModel.started_at.desc())
                .limit(limit)
            )
            run_rows = list(session.scalars(runs_stmt).all())
            for r in run_rows:
                session.expunge(r)
            recent = [_serialize_run(r) for r in run_rows]
    return {"scheduled_jobs": scheduled, "recent_runs": recent}


@router.post("/api/notebooks/run-once")
async def api_run_once(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Trigger a one-shot papermill run of a notebook (admin-only).

    Creates a paused :class:`~pointlessql.models.Job` row carrying
    ``kind="papermill"`` + ``config={notebook_path, parameters}`` so
    the run lands in the same audit-trail surfaces as scheduled jobs.
    Immediately fires a manual run via
    :func:`scheduler_service.execute_run`, returned as a fire-and-
    forget :class:`asyncio.Task` — the HTTP response carries
    ``{job_id, job_run_id}`` so the browser can poll
    ``GET /api/jobs/{job_id}/runs`` until the run reaches a terminal
    status. The job stays paused after the run, so it never re-fires
    on a cron tick and stays around purely as an audit-trail anchor.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON with keys ``path`` (relative notebook path) and
            optional ``parameters`` (dict of papermill overrides).

    Returns:
        JSON ``{"job_id": int, "job_run_id": int, "status": "started"}``.

    Raises:
        ValidationError: When ``path`` is missing / non-string,
            ``parameters`` is not a dict, or the path resolution
            (escape / suffix / existence) rejects the input.
    """  # noqa: DOC502
    import asyncio
    import json as _json
    from datetime import UTC, datetime

    from croniter import croniter as _croniter

    from pointlessql.api._audit_helpers import audit
    from pointlessql.api.dependencies import get_user
    from pointlessql.api.jobs_routes import JOB_REGISTRY
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel

    require_admin(request)
    user = get_user(request)
    settings: Settings = request.app.state.settings

    path = body.get("path")
    if not isinstance(path, str) or not path:
        raise ValidationError("`path` is required")
    parameters = body.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValidationError("`parameters` must be a JSON object")

    # Path validation reuses the executor's resolver, which rejects
    # absolute paths, missing files, traversal, and bad suffixes.
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        path,
    )
    # Touch ``resolved`` to keep the lint happy + the import alive.
    _ = resolved

    # A cron expression we never want to re-fire on. ``is_paused=True``
    # already gates the scheduler, but pinning a far-future minute as a
    # second line of defence keeps the row inert if a future operator
    # ever unpauses it by accident.
    cron_expr = "0 0 1 1 *"
    if not _croniter.is_valid(cron_expr):
        # Should never happen — croniter accepts the canonical 5-field form.
        raise ValidationError("internal: cron sentinel rejected by croniter")

    stamp = datetime.now(UTC)
    safe_path = path.replace("/", "_").replace(".", "_")
    job_name = (
        f"notebook-runonce:{safe_path}:{user['id']}:"
        f"{stamp.strftime('%Y%m%d-%H%M%S-%f')}"
    )
    config_blob = _json.dumps(
        {"notebook_path": path, "parameters": parameters},
    )

    factory = request.app.state.session_factory
    with factory() as session:
        job = JobModel(
            name=job_name,
            cron_expr=cron_expr,
            run_as_user_id=int(user["id"]),
            kind="papermill",
            config=config_blob,
            is_paused=True,
            max_parallel_runs=1,
            on_failure_url=None,
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = int(job.id)
        # Phase 67.4 link-table write — keeps run-once jobs visible in
        # the editor's notebook-jobs panel just like scheduled jobs.
        from pointlessql.models import NotebookJobLink as _NJL

        session.add(
            _NJL(
                workspace_id=1,
                notebook_path=path,
                job_id=job_id,
                created_at=stamp,
            ),
        )
        session.commit()
        # Pre-insert the JobRun row so the browser can poll immediately;
        # ``execute_run`` will update its status as the run progresses.
        # Actually, ``execute_run`` inserts its own JobRun — we just
        # capture the resulting run id by reading the latest row after
        # the task spawns. Re-read pattern matches ``api_run_job``.

    # Fire-and-forget — the HTTP response returns as soon as the task is
    # scheduled. The browser polls ``/api/jobs/{job_id}/runs`` for
    # status.
    asyncio.create_task(
        scheduler_service.execute_run(
            factory, settings, JOB_REGISTRY, job_id, "manual",
        ),
    )

    # Capture the freshly-created JobRun row id with a short retry —
    # ``execute_run`` inserts the row on entry, so a tiny grace gives
    # the task scheduler one tick to make it visible. Five retries with
    # 20 ms spacing is well under any user-perceptible delay.
    job_run_id: int | None = None
    for _ in range(5):
        with factory() as session:
            row = (
                session.query(JobRunModel)
                .filter(JobRunModel.job_id == job_id)
                .order_by(JobRunModel.id.desc())
                .first()
            )
            if row is not None:
                job_run_id = int(row.id)
                break
        await asyncio.sleep(0.02)

    await audit(request, "run_once_notebook", f"notebook:{path}")
    return JSONResponse(
        {
            "job_id": job_id,
            "job_run_id": job_run_id,
            "status": "started",
        },
    )


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


@router.get("/api/notebooks/load")
async def api_load_notebook(request: Request, path: str) -> JSONResponse:
    """Load a ``.py`` notebook + its persisted outputs.

    The browser editor calls this on page-mount.  Returns the cell list
    (with content_hashes) plus every persisted output frame keyed by
    ``(content_hash, kernel_session_id)``.  Re-render cost on a page
    reload stays close to free — kernel-message replay happens
    client-side from the embedded JSON, no extra fetch.

    Args:
        request: Incoming FastAPI request; admin-only for now (the
            workspace gate matches the read-only notebooks page).
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        JSON ``{path, dirty, cells: [...], outputs: [...]}``.
        Each cell carries ``id`` (transient ordinal), ``content_hash``,
        ``cell_type``, ``source``, ``result_var``.  Each output carries
        ``content_hash``, ``kernel_session_id``, ``output_index``,
        ``msg_type``, ``content``, ``metadata``, ``created_at``.

    Raises:
        ValidationError: When the path is missing / outside the
            workspace / wrong suffix / does not exist.  Surfaces
            via :func:`resolve_py_notebook_path`.
    """  # noqa: DOC502
    require_admin(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    document = notebook_doc_service.load_document(absolute, relative)
    outputs = notebook_outputs_service.load_outputs_for_path(
        request.app.state.session_factory, relative
    )
    cells = [
        {
            "id": cell.id,
            "content_hash": cell.content_hash,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "result_var": cell.result_var,
            "tags": list(cell.tags),
        }
        for cell in document.cells
    ]
    return JSONResponse(
        {
            "path": document.path,
            "dirty": document.dirty,
            "mtime": absolute.stat().st_mtime,
            "cells": cells,
            "outputs": outputs,
        }
    )


@router.post("/api/notebooks/save")
async def api_save_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Persist a notebook's cells back to disk.

    The browser editor sends ``{path, cells, expected_mtime?}``;
    cells are an ordered list of ``{cell_type, source, result_var?}``
    dicts.  When ``expected_mtime`` is supplied and disagrees with
    the current on-disk mtime, the route 409s with
    ``{"error": "mtime_conflict", "current_mtime": <iso>}`` so the
    browser can prompt the user to reload before overwriting.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with ``path``, ``cells``, optional
            ``expected_mtime`` (float seconds since epoch).

    Returns:
        JSON ``{path, mtime, cells: [{content_hash, ...}]}`` on
        success — cells carry the freshly-computed FNV-1a-64
        content_hashes so the browser can clear ``_dirty`` flags.

    Raises:
        ValidationError: When path / cells are malformed or escape
            the workspace root.
    """
    require_admin(request)
    raw_path = body.get("path") if isinstance(body, dict) else None
    raw_cells = body.get("cells") if isinstance(body, dict) else None
    if not isinstance(raw_path, str):
        raise ValidationError("body.path must be a string")
    if not isinstance(raw_cells, list):
        raise ValidationError("body.cells must be a list")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, raw_path, must_exist=True
    )
    expected_mtime = body.get("expected_mtime")
    if isinstance(expected_mtime, (int, float)):
        current_mtime = absolute.stat().st_mtime
        if abs(current_mtime - float(expected_mtime)) > 0.001:
            # Return JSONResponse directly so the structured 409 body
            # survives the central error handler's str-coercion of
            # HTTPException.detail.
            return JSONResponse(
                {
                    "error": "mtime_conflict",
                    "current_mtime": current_mtime,
                },
                status_code=409,
            )
    cells: list[notebook_doc_service.NotebookCell] = []
    for index, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise ValidationError(
                f"body.cells[{index}] must be an object, got {type(raw).__name__}"
            )
        cell_type = raw.get("cell_type", "code")
        if cell_type not in {"code", "markdown", "sql"}:
            raise ValidationError(
                f"body.cells[{index}].cell_type must be one of code/markdown/sql"
            )
        source = raw.get("source", "")
        if not isinstance(source, str):
            raise ValidationError(
                f"body.cells[{index}].source must be a string"
            )
        result_var = raw.get("result_var")
        if result_var is not None and not isinstance(result_var, str):
            raise ValidationError(
                f"body.cells[{index}].result_var must be a string or null"
            )
        raw_tags = raw.get("tags") or []
        if not isinstance(raw_tags, list):
            raise ValidationError(
                f"body.cells[{index}].tags must be a list of strings"
            )
        tags: tuple[str, ...] = tuple(
            t for t in raw_tags if isinstance(t, str) and t
        )
        cells.append(
            notebook_doc_service.NotebookCell(
                id=f"cell-{index}",
                content_hash=notebook_doc_service.compute_content_hash(source),
                cell_type=cell_type,
                source=source,
                result_var=result_var if cell_type == "sql" else None,
                tags=tags,
            )
        )
    notebook_doc_service.save_document(absolute, cells)
    new_mtime = absolute.stat().st_mtime
    out_cells = [
        {
            "id": cell.id,
            "content_hash": cell.content_hash,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "result_var": cell.result_var,
            "tags": list(cell.tags),
        }
        for cell in cells
    ]
    relative = str(absolute.relative_to(notebooks_dir))
    logger.info("saved notebook %s (%d cells)", relative, len(cells))
    return JSONResponse(
        {"path": relative, "mtime": new_mtime, "cells": out_cells}
    )


@router.get("/api/notebooks/cell-history")
async def api_cell_history(
    request: Request,
    path: str = Query(..., min_length=1),
    content_hash: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    """Return the last *limit* run-source rows for one cell.

    Backs the per-cell run-history popover the notebook editor
    surfaces in Sprint 66.7.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path under ``notebooks_dir``.
        content_hash: FNV-1a-64 cell identity.
        limit: Maximum rows to return (1-100, default 20).

    Returns:
        JSON ``{"cell": {"path", "content_hash"}, "runs": [...]}``.
        Each run row carries ``id`` / ``execution_count`` / ``source``
        / ``started_at`` / ``finished_at`` / ``status`` /
        ``kernel_session_id``.
    """
    require_admin(request)
    runs = notebook_outputs_service.list_cell_run_sources(
        request.app.state.session_factory,
        file_path=path,
        content_hash=content_hash,
        limit=limit,
    )
    return JSONResponse(
        {
            "cell": {"path": path, "content_hash": content_hash},
            "runs": runs,
        }
    )


@router.post("/api/notebooks/render-markdown")
async def api_render_markdown(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Render a markdown cell to sanitised HTML.

    Server-side render via the existing markdown-it-py CommonMark
    renderer (HTML disabled in the parser → embedded
    ``<script>`` / ``<iframe>`` tags are escaped at parse time).

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with key ``source`` (markdown text).

    Returns:
        JSON ``{"html": "<rendered fragment>"}``.

    Raises:
        ValidationError: When ``body.source`` is missing / non-string.
    """
    require_admin(request)
    raw = body.get("source") if isinstance(body, dict) else None
    if not isinstance(raw, str):
        raise ValidationError("body.source must be a string")
    html = notebook_render_service.render_markdown_source(raw)
    return JSONResponse({"html": html})


@router.get("/notebooks/edit/{path:path}", response_class=HTMLResponse)
async def notebook_editor_page(request: Request, path: str) -> HTMLResponse:
    """Render the browser notebook editor for a specific ``.py`` file.

    The path is validated against the workspace root before render so
    a bad path 422s before a stale editor frame paints.  The editor
    boots itself from ``GET /api/notebooks/load`` after Alpine mounts.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path, captured by the
            ``{path:path}`` converter (slashes preserved).

    Returns:
        The rendered ``pages/notebook_editor.html`` template.

    Raises:
        ValidationError: When the path is missing / outside the
            workspace / wrong suffix / does not exist.  Surfaces
            via :func:`resolve_py_notebook_path`.
    """  # noqa: DOC502
    require_admin(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return _templates(request).TemplateResponse(
        request,
        "pages/notebook_editor.html",
        {
            "notebook_path": relative,
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


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
