"""Agent-run supervision pages — Sprint 13.2.

Phase 12.12.2 stood these routes up as empty stubs so the nav entry
had a landing page after the browser notebook editor was deleted.
Sprint 13.2 replaces the stubs with live views over the
``agent_runs`` Alembic table: the list query is ordered newest-first
and the detail route joins per-cell outputs + cell runs back to the
owning row for the static, server-rendered card deck the
12.12.1 template family already skeletonised.

Sprint 13.4 will layer the filter bar + admin Approve/Deny buttons
on top; the JSON endpoints for those buttons already live on
:mod:`pointlessql.api.agent_runs_routes`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api.agent_runs_routes import serialize_agent_run
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import NotebookCellRun, NotebookOutput
from pointlessql.models.agent_runs import AgentRun
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import output_rendering as output_rendering_service
from pointlessql.settings import Settings

router = APIRouter(tags=["runs"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def _load_runs(request: Request, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch the most recent agent-run rows as serialized dicts.

    Args:
        request: Incoming FastAPI request.
        limit: Max rows to return; the list page caps at the table
            renderer's natural size.

    Returns:
        One dict per row, newest-first, as shaped by
        :func:`serialize_agent_run`.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
        rows = list(session.scalars(stmt).all())
        return [serialize_agent_run(row) for row in rows]


def _load_run(request: Request, run_id: str) -> AgentRun:
    """Load a single agent-run row or raise :class:`CatalogNotFoundError`.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string from the URL.

    Returns:
        The detached ORM row.

    Raises:
        CatalogNotFoundError: No run with that id exists.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        session.expunge(row)
        return row


def _load_outputs_for_run(
    request: Request, run_id: str,
) -> dict[str, list[output_rendering_service.RenderedOutput]]:
    """Group rendered output frames by ``content_hash`` for the template.

    Sprint-60 shipped a generic ``load_outputs_for_path`` helper, but
    the run-detail view wants outputs scoped to *one* run — otherwise
    re-runs of the same notebook path would smear into a single card
    deck.  This query therefore filters on ``agent_run_id`` and orders
    by ``(content_hash, output_index, created_at)`` so the partial
    renders frames in their original Jupyter emit order.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        ``{content_hash: [RenderedOutput, ...]}`` — the shape
        ``run_view.html`` expects under the ``cell_outputs`` key.
    """
    factory = request.app.state.session_factory
    grouped: dict[str, list[output_rendering_service.RenderedOutput]] = defaultdict(list)
    with factory() as session:
        stmt = (
            select(NotebookOutput)
            .where(NotebookOutput.agent_run_id == run_id)
            .order_by(
                NotebookOutput.content_hash,
                NotebookOutput.output_index,
                NotebookOutput.created_at,
            )
        )
        for row in session.scalars(stmt).all():
            try:
                content = json.loads(row.mime_bundle)
            except json.JSONDecodeError:
                continue
            frame = output_rendering_service.render_output_frame(row.msg_type, content)
            grouped[row.content_hash].append(frame)
    return dict(grouped)


def _load_cell_runs_for_run(
    request: Request, run_id: str,
) -> dict[str, dict[str, Any]]:
    """Map ``content_hash`` to the latest per-cell run metadata.

    The run-detail template renders an execution-count badge + status
    pill + duration per cell; this query provides one dict per cell
    that appeared in the run.  Runs that never executed a given cell
    simply omit it, and the template falls back to an empty ``[ ]``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        ``{content_hash: {"execution_count", "duration_ms",
        "status"}}``.  ``duration_ms`` is computed from the row's
        timestamps; ``None`` when the cell never finished.
    """
    factory = request.app.state.session_factory
    out: dict[str, dict[str, Any]] = {}
    with factory() as session:
        stmt = select(NotebookCellRun).where(NotebookCellRun.agent_run_id == run_id)
        for row in session.scalars(stmt).all():
            duration_ms: int | None = None
            if row.finished_at is not None and row.started_at is not None:
                duration_ms = int(
                    (row.finished_at - row.started_at).total_seconds() * 1000
                )
            out[row.content_hash] = {
                "execution_count": row.execution_count,
                "duration_ms": duration_ms,
                "status": row.status,
            }
    return out


@router.get("/runs", response_class=HTMLResponse)
async def runs_list_page(request: Request) -> HTMLResponse:
    """Render the supervision list of agent runs.

    Sprint 13.2 drops the empty-state stub in favour of a live table.
    The filter bar + admin-only Approve/Deny column land in Sprint
    13.4 — until then the page is a plain newest-first overview with
    drill-down links into ``/runs/{id}``.

    Args:
        request: Incoming FastAPI request; auth is enforced by
            app-wide middleware.

    Returns:
        ``pages/runs_list.html`` populated with up to 200 runs.
    """
    runs = _load_runs(request)
    return _templates(request).TemplateResponse(
        request,
        "pages/runs_list.html",
        {
            "runs": runs,
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/runs")
async def runs_list_api(request: Request) -> dict[str, Any]:
    """JSON sibling of ``GET /runs`` for machine consumers."""
    return {"runs": _load_runs(request)}


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_page(request: Request, run_id: str) -> HTMLResponse:
    """Render the per-run supervision view.

    Loads the ``agent_runs`` row, parses the referenced ``.py``
    notebook into ordered cells via
    :func:`pointlessql.services.notebook_doc.load_document`, and
    layers the persisted per-cell outputs + run lifecycle on top.
    When the notebook file is missing (agent wrote a run row but the
    file has been deleted or moved), the template still shows the
    run metadata card and an empty cell list — the supervision
    record is authoritative even if the source is gone.

    Args:
        request: Incoming FastAPI request.
        run_id: Run UUID from the URL.

    Returns:
        ``pages/run_view.html`` with ``run``, ``cells``,
        ``cell_outputs``, ``cell_runs``, and the ``render_markdown``
        helper in context.
    """
    run_row = _load_run(request, run_id)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute_path = (notebooks_dir / run_row.notebook_path).resolve()

    cells: list[notebook_doc_service.NotebookCell] = []
    try:
        if absolute_path.is_file() and absolute_path.is_relative_to(notebooks_dir):
            document = notebook_doc_service.load_document(absolute_path, run_row.notebook_path)
            cells = list(document.cells)
    except (OSError, ValueError):
        cells = []

    return _templates(request).TemplateResponse(
        request,
        "pages/run_view.html",
        {
            "notebook_path": run_row.notebook_path,
            "cells": cells,
            "cell_outputs": _load_outputs_for_run(request, run_id),
            "cell_runs": _load_cell_runs_for_run(request, run_id),
            "run": serialize_agent_run(run_row),
            "render_markdown": output_rendering_service.render_markdown_source,
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
