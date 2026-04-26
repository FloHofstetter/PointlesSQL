"""Agent-run supervision pages.

Server-rendered HTML views over the ``agent_runs`` table: the list
query is ordered newest-first and the detail route joins per-cell
outputs + cell runs, operations, tool calls, lifecycle events, and
attributed queries back to the owning row for the supervision card
deck.

The JSON endpoints these pages link to (Approve/Deny, run summary,
diff, …) live on :mod:`pointlessql.api.agent_runs_routes`.
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
from pointlessql.api.dependencies import get_uc_client
from pointlessql.conventions import load_conventions
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import (
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
    AuditLog,
    NotebookCellRun,
    NotebookOutput,
    QueryHistory,
)
from pointlessql.models.agent_runs import AgentRun
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import output_rendering as output_rendering_service
from pointlessql.services.conformance import (
    ConformanceFinding,
    check_table_against_layer,
    infer_layer_from_full_name,
)
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


def _load_audit_entries_for_run(
    request: Request,
    run_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the audit-log rows whose ``target`` references this run.

    Surfaces the audit trail next to the run metadata so the
    operator can see who created / approved / denied the run
    without leaving the detail page.  Both the registry routes
    and the Approve / Deny buttons write rows with
    ``target = "agent_run:{run_id}"``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.
        limit: Hard cap on rows returned; the sidebar is small.

    Returns:
        List of dicts in newest-first order.
    """
    factory = request.app.state.session_factory
    target_str = f"agent_run:{run_id}"
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AuditLog)
            .where(AuditLog.target == target_str)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "action": row.action,
                    "actor_email": row.user_email,
                    "actor_role": row.actor_role,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "detail": row.detail,
                }
            )
    return out


def _load_lineage_summary_for_run(
    request: Request,
    run_id: str,
) -> dict[str, Any]:
    """Aggregate Sprint-15.3 ``lineage_row_edges`` per operation.

    Joins ``lineage_row_edges`` against ``agent_run_operations`` so
    the run-detail Lineage tab can render one row per op with
    source/target FQNs, op name, and edge count.  Operations with no
    recorded edges are excluded (the empty-state alert covers that).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Dict shaped ``{"total_edges": int, "rows": [{
        "ordinal": int, "op_name": str, "source_table": str,
        "target_table": str, "edge_count": int}, ...]}`` ready to
        feed the run-detail Lineage tab.
    """
    from sqlalchemy import func

    from pointlessql.models import LineageRowEdge

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    total = 0
    with factory() as session:
        stmt = (
            select(
                AgentRunOperation.id,
                AgentRunOperation.ordinal,
                AgentRunOperation.op_name,
                AgentRunOperation.target_table,
                LineageRowEdge.source_table,
                func.count(LineageRowEdge.id).label("edge_count"),
            )
            .join(LineageRowEdge, LineageRowEdge.op_id == AgentRunOperation.id)
            .where(AgentRunOperation.agent_run_id == run_id)
            .group_by(
                AgentRunOperation.id,
                AgentRunOperation.ordinal,
                AgentRunOperation.op_name,
                AgentRunOperation.target_table,
                LineageRowEdge.source_table,
            )
            .order_by(AgentRunOperation.ordinal)
        )
        for row in session.execute(stmt).all():
            edge_count = int(row[5])
            total += edge_count
            rows.append(
                {
                    "ordinal": int(row[1]),
                    "op_name": row[2],
                    "target_table": row[3],
                    "source_table": row[4],
                    "edge_count": edge_count,
                }
            )
    return {"total_edges": total, "rows": rows}


def _load_rejects_for_run(request: Request, run_id: str) -> list[dict[str, Any]]:
    """Return Sprint-15.5.3 ``lineage_row_rejects`` for the run-detail tab.

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.

    Returns:
        List of dicts shaped ``{"op_id", "source_table",
        "source_row_id", "reason", "detail", "created_at"}`` in
        insertion order.  Empty list when no rejects were recorded
        (default — ``track_rejects=True`` not set on any merge call
        in the run).
    """
    from pointlessql.models import LineageRowReject

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageRowReject)
            .where(LineageRowReject.run_id == run_id)
            .order_by(LineageRowReject.id)
        )
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "source_table": r.source_table,
                    "source_row_id": r.source_row_id,
                    "reason": r.reason,
                    "detail": r.detail,
                    "created_at": r.created_at,
                }
            )
    return rows


async def _load_uc_mutations_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return soyuz audit-log rows attributed to *run_id*.

    Asks soyuz's ``GET /audit-log?agent_run_id=`` cross-reference
    surface (PointlesSQL Sprint 14.4 / soyuz `v0.2.0rc3`).  Returns
    ``[]`` against older soyuz versions that lack the endpoint —
    the run-detail "UC mutations" tab simply renders empty.

    Args:
        request: Incoming FastAPI request — provides
            ``app.state.uc_client``.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Raw soyuz JSON dicts (``id`` / ``action`` / ``target`` /
        ``principal`` / ``agent_run_id`` / ``client_ip`` /
        ``detail`` / ``created_at``) ready for the template.
    """
    from pointlessql.services import soyuz_audit

    uc = request.app.state.uc_client
    return await soyuz_audit.fetch_for_run(uc, run_id, limit=200)


def _load_unattributed_for_run(
    request: Request,
    *,
    tables_touched: list[str],
) -> list[dict[str, Any]]:
    """Return ``unattributed_writes`` rows on tables this run touched.

    Filters to rows with ``acknowledged_at IS NULL`` so the
    run-detail surface highlights only the queue admins still need
    to triage.  Empty list when ``tables_touched`` is empty (no
    join surface) or no unacknowledged writes exist.

    Args:
        request: Incoming FastAPI request.
        tables_touched: Three-part UC names from the run's
            ``tables_touched`` JSON.

    Returns:
        List of dicts shaped like the admin page's entries.
    """
    if not tables_touched:
        return []
    from pointlessql.models import UnattributedWrite

    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(UnattributedWrite)
            .where(
                UnattributedWrite.table_fqn.in_(tables_touched),
                UnattributedWrite.acknowledged_at.is_(None),
            )
            .order_by(UnattributedWrite.detected_at.desc())
            .limit(50)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "table_fqn": row.table_fqn,
                    "delta_version": row.delta_version,
                    "commit_timestamp": (
                        row.commit_timestamp.isoformat() if row.commit_timestamp else None
                    ),
                    "detected_at": row.detected_at.isoformat(),
                }
            )
    return out


def _load_operations_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ``agent_run_operations`` rows for *run_id* in ordinal order.

    The per-operation trail emitted by the PQL primitives.  Ordered
    by ``ordinal ASC`` so the run-detail Operations tab reads
    top-to-bottom in execution order.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts ready to feed into the Jinja template.
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunOperation)
            .where(AgentRunOperation.agent_run_id == run_id)
            .order_by(AgentRunOperation.ordinal)
        )
        rows = list(session.scalars(stmt).all())

    op_ids = [row.id for row in rows]
    column_edge_counts: dict[int, int] = {}
    value_change_counts: dict[int, int] = {}
    if op_ids:
        try:
            from pointlessql.services.lineage_edges import count_column_edges_for_op

            column_edge_counts = count_column_edges_for_op(factory, op_ids)
        except Exception:  # noqa: BLE001 — best-effort badge population
            column_edge_counts = {}
        try:
            from pointlessql.services.lineage_edges import count_value_changes_for_op

            value_change_counts = count_value_changes_for_op(factory, op_ids)
        except Exception:  # noqa: BLE001 — best-effort badge population
            value_change_counts = {}

    for row in rows:
        duration_ms: int | None = None
        if row.finished_at is not None and row.started_at is not None:
            duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
        try:
            params = json.loads(row.params_json)
        except json.JSONDecodeError:
            params = {}
        out.append(
            {
                "id": row.id,
                "ordinal": row.ordinal,
                "op_name": row.op_name,
                "params": params,
                "target_table": row.target_table,
                "input_sha": row.input_sha,
                "rows_affected": row.rows_affected,
                "delta_version_before": row.delta_version_before,
                "delta_version_after": row.delta_version_after,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": (row.finished_at.isoformat() if row.finished_at else None),
                "duration_ms": duration_ms,
                "error_message": row.error_message,
                "status": "error" if row.error_message else "ok",
                "column_edges_count": column_edge_counts.get(row.id, 0),
                "value_changes_count": value_change_counts.get(row.id, 0),
            }
        )
    return out


def _load_source_for_run(
    request: Request,
    run_id: str,
) -> dict[str, Any] | None:
    """Return the captured ``.py`` source row for *run_id* or ``None``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        ``{"source_bytes", "source_sha", "captured_at"}`` or ``None``
        when no source was captured (run predates the forced
        source-capture contract).
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRunSource).where(AgentRunSource.agent_run_id == run_id))
        if row is None:
            return None
        return {
            "source_bytes": row.source_bytes,
            "source_sha": row.source_sha,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        }


def _load_events_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all CloudEvents lifecycle rows for *run_id*, oldest first.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts with ``event_type``, ``fired_at``, ``outcome``,
        ``event_id``.  Empty list when no events were persisted
        (run predates the lifecycle-event capture contract).
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunEvent)
            .where(AgentRunEvent.agent_run_id == run_id)
            .order_by(AgentRunEvent.fired_at)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "fired_at": row.fired_at.isoformat() if row.fired_at else None,
                    "outcome": row.outcome,
                }
            )
    return out


def _load_queries_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ``query_history`` rows attributed to *run_id*.

    Backs the run-detail view's Queries tab.  Ordered by
    ``started_at DESC`` so the most recent execution sits at the
    top, mirroring the standalone ``/queries`` page.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts with ``id``, ``sql_text``, ``status``,
        ``row_count``, ``duration_ms``, ``started_at``, and
        ``error_message``.
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(QueryHistory)
            .where(QueryHistory.agent_run_id == run_id)
            .order_by(QueryHistory.started_at.desc())
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "sql_text": row.sql_text,
                    "status": row.status,
                    "row_count": row.row_count,
                    "duration_ms": row.duration_ms,
                    "started_at": (row.started_at.isoformat() if row.started_at else None),
                    "error_message": row.error_message,
                }
            )
    return out


def _load_tool_calls_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ``agent_run_tool_calls`` rows for *run_id*, oldest first.

    Surfaces the LLM reasoning trace persisted by the
    ``POST /api/agent-runs/{id}/tool-call`` route.  Tool calls are
    a fourth orthogonal level alongside cells / operations /
    queries: cells = source layout, operations = PQL primitive
    writes, queries = ad-hoc SQL, tool calls = which LLM tool the
    agent invoked (``pql_conventions``, ``pql_query``, …).  Ordered
    by ``called_at ASC`` so the tab reads top-to-bottom in
    invocation order.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts ready to feed into the Jinja template.
        ``args_json`` and ``result_summary`` are passed through
        verbatim — the template handles the truncation for display.
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunToolCall)
            .where(AgentRunToolCall.agent_run_id == run_id)
            .order_by(AgentRunToolCall.called_at)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "tool_name": row.tool_name,
                    "args_json": row.args_json,
                    "result_summary": row.result_summary,
                    "duration_ms": row.duration_ms,
                    "called_at": (row.called_at.isoformat() if row.called_at else None),
                }
            )
    return out


def _load_cell_runs_for_run(
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


@router.get("/runs", response_class=HTMLResponse)
async def runs_list_page(request: Request) -> HTMLResponse:
    """Render the supervision list of agent runs.

    A newest-first overview with drill-down links into
    ``/runs/{id}``; the filter bar + admin-only Approve/Deny column
    are layered on top in the template.

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


@router.get("/api/agent-runs/{run_id}/full")
async def api_agent_run_full(request: Request, run_id: str) -> dict[str, Any]:
    """Return the full supervision payload for *run_id* in one round-trip.

    Backs the ``pql_my_run`` Hermes tool.  Joins the serialised
    :class:`AgentRun` row with every per-run sibling table the
    supervision view already aggregates: source bytes, operations,
    tool-call trail, lifecycle events, attributed query history.
    Lives next to the ``_load_*`` helpers it reuses to avoid a
    circular import back into ``agent_runs_routes``.

    The route is read-only and gated only by the standard auth
    middleware — any working-agent that already knows its own
    ``run_id`` (because PointlesSQL gave it that id at registration
    time) can ask the supervisor record for the full picture before
    deciding what to write next.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string from the URL.

    Returns:
        ``{"run": {...}, "source": {...}|None, "operations": [...],
        "tool_calls": [...], "events": [...], "queries": [...]}``.
        :func:`_load_run` raises :class:`CatalogNotFoundError` when
        no row with that id exists; FastAPI's exception handlers
        translate that into a 404 response.
    """
    run_row = _load_run(request, run_id)
    return {
        "run": serialize_agent_run(run_row),
        "source": _load_source_for_run(request, run_id),
        "operations": _load_operations_for_run(request, run_id),
        "tool_calls": _load_tool_calls_for_run(request, run_id),
        "events": _load_events_for_run(request, run_id),
        "queries": _load_queries_for_run(request, run_id),
    }


async def _conformance_findings_for_run(
    request: Request, tables_touched: list[str]
) -> list[ConformanceFinding]:
    """Run the conformance checks for each touched table.

    Loads the conventions once, then walks ``tables_touched`` in
    order.  Each table is fetched via the soyuz UC client; missing
    tables (typo, race with a drop, transient catalog hiccup) are
    silently skipped — the conformance check is a passive surface,
    so noise from the check itself defeats the purpose.

    Args:
        request: Incoming FastAPI request — provides the
            principal-scoped UC client.
        tables_touched: Three-part UC names from the agent-run
            ``tables_touched`` JSON.

    Returns:
        Flat list of findings across all touched tables.  Empty
        when no tables are listed or none have detectable
        violations.
    """
    if not tables_touched:
        return []

    conventions = load_conventions()
    client = get_uc_client(request)
    findings: list[ConformanceFinding] = []

    for full_name in tables_touched:
        layer = infer_layer_from_full_name(full_name, conventions)
        if layer is None:
            continue
        parts = full_name.split(".")
        if len(parts) != 3:
            continue
        try:
            table_info = await client.get_table(parts[0], parts[1], parts[2])
        except Exception:  # noqa: BLE001 — passive surface, never raise into the route
            continue
        if not table_info:
            continue
        columns_raw = table_info.get("columns") or []
        column_names: list[str] = []
        for col in columns_raw:
            if isinstance(col, dict):
                name = col.get("name")
                if isinstance(name, str):
                    column_names.append(name)
        findings.extend(
            check_table_against_layer(
                table_full_name=full_name,
                layer=layer,
                column_names=column_names,
                conventions=conventions,
            )
        )

    return findings


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
        ``cell_outputs``, ``cell_runs``, ``tool_calls``, and the
        ``render_markdown`` helper in context.
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
    except OSError, ValueError:
        cells = []

    return _templates(request).TemplateResponse(
        request,
        "pages/run_view.html",
        {
            "notebook_path": run_row.notebook_path,
            "cells": cells,
            "cell_outputs": _load_outputs_for_run(request, run_id),
            "cell_runs": _load_cell_runs_for_run(request, run_id),
            "audit_entries": _load_audit_entries_for_run(request, run_id),
            "operations": _load_operations_for_run(request, run_id),
            "source": _load_source_for_run(request, run_id),
            "events": _load_events_for_run(request, run_id),
            "queries": _load_queries_for_run(request, run_id),
            "tool_calls": _load_tool_calls_for_run(request, run_id),
            "conformance_findings": [
                {
                    "table_full_name": f.table_full_name,
                    "layer": f.layer,
                    "severity": f.severity,
                    "code": f.code,
                    "message": f.message,
                }
                for f in await _conformance_findings_for_run(
                    request, list(serialize_agent_run(run_row).get("tables_touched", []))
                )
            ],
            "unattributed_writes": _load_unattributed_for_run(
                request,
                tables_touched=list(serialize_agent_run(run_row).get("tables_touched", [])),
            ),
            "uc_mutations": await _load_uc_mutations_for_run(request, run_id),
            "lineage_summary": _load_lineage_summary_for_run(request, run_id),
            "rejects": _load_rejects_for_run(request, run_id),
            "run": serialize_agent_run(run_row),
            "render_markdown": output_rendering_service.render_markdown_source,
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
