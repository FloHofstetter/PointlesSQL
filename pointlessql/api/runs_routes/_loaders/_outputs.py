"""Cell-output axis — rendered outputs + per-cell run metadata."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.models import NotebookCellRun, NotebookOutput
from pointlessql.services import output_rendering as output_rendering_service


def load_outputs_for_run(
    request: Request,
    run_id: str,
) -> dict[str, list[output_rendering_service.RenderedOutput]]:
    """Group rendered output frames by ``content_hash`` for the template.

    A generic ``load_outputs_for_path`` helper already exists, but
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


def load_cell_runs_for_run(
    request: Request,
    run_id: str,
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
                duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
            out[row.content_hash] = {
                "execution_count": row.execution_count,
                "duration_ms": duration_ms,
                "status": row.status,
            }
    return out
