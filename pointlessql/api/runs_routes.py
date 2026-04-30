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

import asyncio
import datetime
import json
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.agent_runs_routes import serialize_agent_run
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
    require_supervisor,
)
from pointlessql.conventions import load_conventions
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
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
from pointlessql.services.agent_runs.events import (
    EVENT_TYPE_ROLLBACK_EXECUTED,
    emit_agent_run_event,
)
from pointlessql.services.agent_runs.operations import (
    RollbackAmbiguous,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)
from pointlessql.services.cascade import find_downstream_tables
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


def load_lineage_summary_for_run(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate Sprint-15.3 ``lineage_row_edges`` per operation.

    Joins ``lineage_row_edges`` against ``agent_run_operations`` so
    the run-detail Lineage tab can render one row per op with
    source/target FQNs, op name, and edge count.  Operations with no
    recorded edges are excluded (the empty-state alert covers that).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id: Sprint 18.1 cross-axis filter — when set, restrict
            the aggregate to a single op.

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
        if op_id is not None:
            stmt = stmt.where(AgentRunOperation.id == op_id)
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


def load_rejects_for_run(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return Sprint-15.5.3 ``lineage_row_rejects`` for the run-detail tab.

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id: Sprint 18.1 cross-axis filter — when set, restrict
            to rejects produced by this single op.  ``None`` keeps
            the full run-scoped list.

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
        if op_id is not None:
            stmt = stmt.where(LineageRowReject.op_id == op_id)
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


def load_unattributed_for_run(
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
    *,
    op_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return all ``agent_run_operations`` rows for *run_id* in ordinal order.

    The per-operation trail emitted by the PQL primitives.  Ordered
    by ``ordinal ASC`` so the run-detail Operations tab reads
    top-to-bottom in execution order.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.
        op_id: Sprint 18.1 cross-axis filter — when set, only the
            single op with this id is returned (still as a one-row
            list so the template stays branchless).  ``None`` keeps
            the full ordered list.

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
        if op_id is not None:
            stmt = stmt.where(AgentRunOperation.id == op_id)
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
        training_params: dict[str, Any] | None = None
        if row.training_params_json:
            try:
                parsed_tp = json.loads(row.training_params_json)
                if isinstance(parsed_tp, dict):
                    training_params = {
                        "params": parsed_tp.get("params") or {},
                        "metrics": parsed_tp.get("metrics") or {},
                    }
            except json.JSONDecodeError:
                training_params = None
        env_snapshot: dict[str, Any] | None = None
        if row.env_snapshot:
            try:
                parsed_env = json.loads(row.env_snapshot)
                if isinstance(parsed_env, dict):
                    env_snapshot = parsed_env
            except json.JSONDecodeError:
                env_snapshot = None
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
                "training_params": training_params,
                "env_snapshot": env_snapshot,
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
async def run_detail_page(
    request: Request,
    run_id: str,
    op_id: int | None = None,
) -> HTMLResponse:
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
        op_id: Sprint 18.1 cross-axis deep-link.  When set, every
            tab whose surface has an ``op_id`` linkage (Operations,
            Rejects, Lineage) renders pre-filtered to this single
            op; tabs without that linkage render unfiltered with a
            visible "(filter inactive on this surface)" hint.

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

    # ``filter_op_ordinal`` is the human-friendly label rendered in
    # the cross-axis chip; the deep link carries the integer id.
    filter_op_ordinal: int | None = None
    if op_id is not None:
        ops_for_label = _load_operations_for_run(request, run_id, op_id=op_id)
        if ops_for_label:
            filter_op_ordinal = int(ops_for_label[0]["ordinal"])
        else:
            # Stale link (op deleted, run rerun, ...) — fall back to
            # unfiltered view rather than 404; cockpit drill-downs
            # should be permissive.
            op_id = None

    # Sprint 18.5 — run-detail anomaly chip.  Best-effort: if the
    # aggregator fails the run still renders without the chip.
    run_anomaly: dict[str, Any] | None = _run_anomaly_chip(request, run_id)

    return _templates(request).TemplateResponse(
        request,
        "pages/run_view.html",
        {
            "notebook_path": run_row.notebook_path,
            "cells": cells,
            "cell_outputs": _load_outputs_for_run(request, run_id),
            "cell_runs": _load_cell_runs_for_run(request, run_id),
            "audit_entries": _load_audit_entries_for_run(request, run_id),
            "operations": _load_operations_for_run(request, run_id, op_id=op_id),
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
            "unattributed_writes": load_unattributed_for_run(
                request,
                tables_touched=list(serialize_agent_run(run_row).get("tables_touched", [])),
            ),
            "uc_mutations": await _load_uc_mutations_for_run(request, run_id),
            "lineage_summary": load_lineage_summary_for_run(request, run_id, op_id=op_id),
            "rejects": load_rejects_for_run(request, run_id, op_id=op_id),
            "rollback_targets": _rollback_targets_for_run(request, run_id),
            "run": serialize_agent_run(run_row),
            "render_markdown": output_rendering_service.render_markdown_source,
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "filter_op_id": op_id,
            "filter_op_ordinal": filter_op_ordinal,
            "run_anomaly": run_anomaly,
        },
    )


def _rollback_targets_for_run(request: Request, run_id: str) -> list[str]:
    """Return de-duplicated ``target_table`` names this run wrote to.

    Drives the Rollback dropdown menu in ``run_view.html``.  Only
    write-shaped op names contribute (``merge`` / ``write_table`` /
    ``autoload`` / ``aggregate``); ``sql`` and prior ``rollback``
    ops are excluded so the menu doesn't offer to rollback a read
    or a rollback (rollback-of-rollback is technically possible but
    the v1 UX leaves it to direct API calls).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Sorted list of distinct target table FQNs.  Empty when the
        run wrote nothing (notebook ran only ``pql.sql`` reads).
    """
    write_ops = ("merge", "write_table", "autoload", "aggregate")
    factory = request.app.state.session_factory
    targets: set[str] = set()
    with factory() as session:
        rows = session.scalars(
            select(AgentRunOperation.target_table)
            .where(AgentRunOperation.agent_run_id == run_id)
            .where(AgentRunOperation.op_name.in_(write_ops))
            .where(AgentRunOperation.target_table.is_not(None))
        )
        for value in rows:
            if value:
                targets.add(value)
    return sorted(targets)


@router.get("/api/runs/{run_id}/graph")
async def api_run_graph(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
) -> dict[str, Any]:
    """Return the unified row + column lineage DAG for one run.

    Sprint 17.3 — backbone for the Lineage / Graph sub-tab on
    ``/runs/{id}``.  Joins :class:`pointlessql.models.LineageRowEdge`
    and :class:`pointlessql.models.LineageColumnMap` per
    ``run_id`` (and optional ``op_id``) into a single
    cytoscape-shaped payload — one node per touched table, one
    edge per ``(source, target, op_id)`` triple, with the
    underlying ``column_pairs`` carried alongside so the
    frontend's column-click handler can highlight upstream and
    downstream simultaneously without a second round-trip.

    The route follows the auditor / supervisor scope ladder that
    Sprint 19.1 set for the per-run audit-axis JSON endpoints —
    same data already visible on the run-detail Lineage tab,
    just rearranged.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional op filter.  When set, only edges + nodes
            touched by this op are emitted.

    Returns:
        ``{"run_id", "op_id", "nodes": [...], "edges": [...]}``.
        See :func:`pointlessql.services.lineage_graph_builder.build_lineage_graph`
        for the full per-element shape.

    Raises:
        AuthorizationError: Caller lacks the supervisor or auditor
            scope.
        CatalogNotFoundError: No run with that id.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    with factory() as session:
        if session.scalar(select(AgentRun).where(AgentRun.id == run_id)) is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
    from pointlessql.services.lineage_graph_builder import build_lineage_graph

    return build_lineage_graph(request, run_id, op_id=op_id)


@router.get("/api/runs/{run_id}/rollback-preview")
async def api_rollback_preview(
    request: Request,
    run_id: str,
    target: str = Query(description="UC catalog.schema.table to preview rollback for"),
) -> dict[str, Any]:
    """Preview what ``pql.rollback`` would do for ``(run_id, target)``.

    Returns the version delta that would be restored, a flag for
    whether the table moved past the targeted op (staleness),
    a list of intervening ``agent_run_operations`` rows that would
    be overwritten on a forced rollback, and a list of downstream
    tables that derived data from the target via row + column
    lineage.  When the run touched the target more than once the
    response carries ``op_candidates`` and ``op_id: null`` so the
    caller can pick by ordinal.

    The route is admin-only — rollback itself is admin-only and the
    preview leaks no information beyond what the admin can already
    see in ``/runs/{id}``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the run whose write is being
            previewed.
        target: Fully-qualified UC name of the target table.

    Returns:
        ``{"run_id", "target_table", "op_id", "op_candidates",
        "delta_version_before", "delta_version_after",
        "current_version", "is_stale", "intervening_writes",
        "downstream_warnings"}``.

    Raises:
        CatalogNotFoundError: No matching ``agent_run_operations``
            row, or the target is unknown to soyuz-catalog.
        ValidationError: The targeted op is a creation
            (``delta_version_before is None``) and rollback would
            mean dropping the table (out of v1 scope).
        AuthorizationError: Non-admin caller.
    """  # noqa: DOC503 — AuthorizationError is raised by require_admin
    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == run_id)
                .where(AgentRunOperation.target_table == target)
                .order_by(AgentRunOperation.ordinal)
            )
        )
        for row in rows:
            session.expunge(row)
    if not rows:
        raise CatalogNotFoundError(f"agent run {run_id!r} did not write to {target!r}")

    op_candidates = [_serialize_op_candidate(row) for row in rows]

    chosen: AgentRunOperation | None = rows[0] if len(rows) == 1 else None

    intervening: list[dict[str, Any]] = []
    current_version: int | None = None
    is_stale: bool = False

    if chosen is not None:
        if chosen.delta_version_before is None:
            raise ValidationError(
                f"agent run {run_id!r} created {target!r} (delta_version_before is None); "
                "rollback would mean dropping the table (out of v1 scope)"
            )
        current_version = await _read_delta_version(request, target)
        if (
            current_version is not None
            and chosen.delta_version_after is not None
            and current_version != chosen.delta_version_after
        ):
            is_stale = True
            intervening = _load_intervening_writes(
                request,
                target=target,
                after_version=chosen.delta_version_after,
                exclude_run=run_id,
            )

    downstream_warnings = [
        {
            "target_table": spec.target_table,
            "via": spec.via,
            "edge_count": spec.edge_count,
            "most_recent_run_id": spec.most_recent_run_id,
        }
        for spec in find_downstream_tables(factory, source_table=target)
    ]

    return {
        "run_id": run_id,
        "target_table": target,
        "op_id": chosen.id if chosen is not None else None,
        "op_candidates": op_candidates,
        "delta_version_before": chosen.delta_version_before if chosen is not None else None,
        "delta_version_after": chosen.delta_version_after if chosen is not None else None,
        "current_version": current_version,
        "is_stale": is_stale,
        "intervening_writes": intervening,
        "downstream_warnings": downstream_warnings,
    }


def _serialize_op_candidate(row: AgentRunOperation) -> dict[str, Any]:
    """Project the columns the rollback-preview UI needs from an op row."""
    return {
        "id": row.id,
        "ordinal": row.ordinal,
        "op_name": row.op_name,
        "delta_version_before": row.delta_version_before,
        "delta_version_after": row.delta_version_after,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


async def _read_delta_version(request: Request, target: str) -> int | None:
    """Read ``DeltaTable.version()`` for *target*, best-effort.

    The preview-render path reaches into Delta to compare the
    targeted op's recorded ``delta_version_after`` to "right now".
    A read failure (table missing, soyuz down) returns ``None`` so
    the modal renders ``"current version: unknown"`` instead of a
    500.

    Args:
        request: Incoming FastAPI request — provides the UC client.
        target: Fully-qualified UC table name.

    Returns:
        The current Delta version, or ``None`` when the version
        couldn't be read.
    """
    try:
        client = get_uc_client(request)
        parts = target.split(".")
        if len(parts) != 3:
            return None
        info = await client.get_table(parts[0], parts[1], parts[2])
        if not info:
            return None
        location = info.get("storage_location")
        if not isinstance(location, str) or not location:
            return None
        from pointlessql.pql._write import safe_delta_version

        return safe_delta_version(location)
    except Exception:  # noqa: BLE001 — preview route is best-effort
        return None


def _load_intervening_writes(
    request: Request,
    *,
    target: str,
    after_version: int,
    exclude_run: str,
) -> list[dict[str, Any]]:
    """Return ``agent_run_operations`` rows that wrote *target* after *after_version*.

    Drives the ⚠ stale-warning panel.  The exclusion is by run id —
    other ops within the same run that share the target ordinal are
    surfaced as ``op_candidates``, not as intervening writes.

    Args:
        request: Incoming FastAPI request — provides the session
            factory.
        target: ``target_table`` to scope the search to.
        after_version: ``delta_version_after`` of the targeted op;
            rows with a strictly greater value are intervening.
        exclude_run: ``agent_run_id`` of the run being rolled back.

    Returns:
        A list of dicts shaped like ``{"run_id", "op_id",
        "delta_version_after", "started_at"}``, ordered by
        ``delta_version_after`` ascending.  Empty when no rows
        match (or the query failed — best-effort).
    """
    factory = request.app.state.session_factory
    try:
        with factory() as session:
            rows = list(
                session.scalars(
                    select(AgentRunOperation)
                    .where(AgentRunOperation.target_table == target)
                    .where(AgentRunOperation.delta_version_after > after_version)
                    .where(AgentRunOperation.agent_run_id != exclude_run)
                    .order_by(AgentRunOperation.delta_version_after)
                )
            )
            return [
                {
                    "run_id": row.agent_run_id,
                    "op_id": row.id,
                    "delta_version_after": row.delta_version_after,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                }
                for row in rows
            ]
    except Exception:  # noqa: BLE001 — preview is best-effort
        return []


@router.post("/api/runs/{run_id}/rollback")
async def api_run_rollback(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Execute ``pql.rollback`` for ``(run_id, target)`` under a fresh run.

    Spawns a brand-new ``agent_runs`` row to host the rollback op,
    invokes :func:`pointlessql.pql._rollback.rollback_table` under
    that run id, and returns the new run id + the version delta on
    success.  Refusal modes from the primitive map to HTTP errors:

    * ``RollbackTargetNotFound`` → 404 ``CatalogNotFoundError``.
    * ``RollbackAmbiguous`` → 409 with ``op_candidates`` payload.
    * ``RollbackInvalid`` → 422 ``ValidationError``.
    * ``RollbackStale`` → 409 with ``current_version`` /
      ``expected_version`` / ``intervening_op_count`` payload.

    On any refusal the spawned rollback run is marked ``failed``
    with ``finished_at`` set so the audit trail records both the
    attempt and the gate that fired.

    A ``pointlessql.rollback.executed`` CloudEvent fires on
    success; the same event family the rest of agent-run lifecycle
    uses.

    Args:
        request: Incoming FastAPI request.
        run_id: ``agent_runs.id`` whose write should be undone.
        body: JSON body with ``target`` (3-part UC name, required),
            ``op_ordinal`` (int, optional — required when the run
            touched the target more than once), ``allow_force``
            (bool, default ``False``).

    Returns:
        ``{"new_run_id", "new_op_id", "version_before",
        "version_after", "target_version_restored",
        "rolled_back_run_id", "target", "allow_force"}``.

    Raises:
        ValidationError: Body shape problem, or the targeted op was
            a creation (drop is out of v1 scope).
        CatalogNotFoundError: No matching op found, or the target
            isn't registered with soyuz.
        AuthorizationError: Non-admin caller.
    """  # noqa: DOC502,DOC503 — refusal exceptions handled via _rollback_refusal_response
    require_admin(request)

    target = body.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a 3-part UC name")
    op_ordinal_raw = body.get("op_ordinal")
    op_ordinal: int | None
    if op_ordinal_raw is None:
        op_ordinal = None
    elif isinstance(op_ordinal_raw, int):
        op_ordinal = op_ordinal_raw
    else:
        raise ValidationError("op_ordinal must be an integer or null")
    allow_force = bool(body.get("allow_force", False))

    factory = request.app.state.session_factory
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")

    new_run_id = str(uuid.uuid4())
    started_at = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        rollback_run = AgentRun(
            id=new_run_id,
            principal=principal or None,
            agent_id="pointlessql.rollback",
            notebook_path=f"rollback-of-{run_id}",
            status="running",
            started_at=started_at,
        )
        session.add(rollback_run)
        session.commit()

    settings: Settings = request.app.state.settings

    def _run_rollback() -> dict[str, Any]:
        from pointlessql.pql.pql import PQL  # noqa: PLC0415 — lazy

        pql = PQL(
            settings=settings,
            principal=principal or None,
            agent_run_id=new_run_id,
        )
        result = pql.rollback(
            target,
            before_run=run_id,
            op_ordinal=op_ordinal,
            allow_force=allow_force,
        )
        return {
            "version_before": result.version_before,
            "version_after": result.version_after,
            "target_version_restored": result.target_version_restored,
            "restored_file_count": result.restored_file_count,
        }

    try:
        result = await asyncio.to_thread(_run_rollback)
    except (RollbackAmbiguous, RollbackStale, RollbackInvalid, RollbackTargetNotFound) as exc:
        _mark_rollback_run_failed(factory, run_id=new_run_id, message=repr(exc))
        raise _refusal_to_http_error(exc) from exc
    except Exception:
        _mark_rollback_run_failed(factory, run_id=new_run_id, message="rollback raised")
        raise

    finished_at = datetime.datetime.now(datetime.UTC)
    new_op_id = _finalise_rollback_run(
        factory,
        run_id=new_run_id,
        finished_at=finished_at,
    )

    payload = {
        "new_run_id": new_run_id,
        "new_op_id": new_op_id,
        "version_before": result["version_before"],
        "version_after": result["version_after"],
        "target_version_restored": result["target_version_restored"],
        "restored_file_count": result["restored_file_count"],
        "rolled_back_run_id": run_id,
        "target": target,
        "allow_force": allow_force,
    }

    await audit(
        request,
        "rollback_run",
        f"agent_run:{run_id}",
        {
            "target": target,
            "new_run_id": new_run_id,
            "version_before": result["version_before"],
            "version_after": result["version_after"],
            "allow_force": allow_force,
        },
    )

    await emit_agent_run_event(
        EVENT_TYPE_ROLLBACK_EXECUTED,
        {
            "id": new_run_id,
            "rolled_back_run_id": run_id,
            "target_table": target,
            "version_before": result["version_before"],
            "version_after": result["version_after"],
            "target_version_restored": result["target_version_restored"],
            "new_op_id": new_op_id,
            "allow_force": allow_force,
        },
        session_factory=factory,
    )

    return payload


def _mark_rollback_run_failed(
    factory: Any,
    *,
    run_id: str,
    message: str,
) -> None:
    """Mark the spawned rollback run as ``failed`` on a refusal.

    Always best-effort — the route is about to re-raise, so a DB
    error here gets swallowed rather than masking the underlying
    rollback exception.

    Args:
        factory: SQLAlchemy session factory.
        run_id: Newly-created ``agent_runs.id`` for the rollback.
        message: Short summary stored on
            ``agent_runs.denied_reason``.
    """
    finished_at = datetime.datetime.now(datetime.UTC)
    try:
        with factory() as session:
            row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if row is None:
                return
            row.status = "failed"
            row.finished_at = finished_at
            row.denied_reason = message[:500]
            session.commit()
    except Exception:  # noqa: BLE001 — best-effort run-marker
        return


def _finalise_rollback_run(
    factory: Any,
    *,
    run_id: str,
    finished_at: datetime.datetime,
) -> int | None:
    """Mark the rollback run ``succeeded`` and return its op id.

    Reads the single ``agent_run_operations`` row the rollback
    primitive emitted (one rollback = one op).  ``None`` is
    returned when no op landed (shouldn't happen on the success
    path, but defensive in case the recorder failed silently).

    Args:
        factory: SQLAlchemy session factory.
        run_id: Newly-created rollback run id.
        finished_at: UTC instant the rollback completed.

    Returns:
        The ``agent_run_operations.id`` for the rollback op, or
        ``None`` when no op exists.
    """
    op_id: int | None = None
    with factory() as session:
        op = session.scalar(
            select(AgentRunOperation)
            .where(AgentRunOperation.agent_run_id == run_id)
            .where(AgentRunOperation.op_name == "rollback")
            .order_by(AgentRunOperation.ordinal.desc())
            .limit(1)
        )
        if op is not None:
            op_id = op.id
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is not None:
            row.status = "succeeded"
            row.finished_at = finished_at
            session.commit()
    return op_id


def _refusal_to_http_error(exc: Exception) -> Exception:
    """Translate a rollback refusal into the centralised HTTP error.

    All four refusal classes are :class:`Exception` subclasses but
    not :class:`PointlessSQLError`, so the centralised handler
    would 500 them.  Map them to the existing domain errors so the
    response shape stays consistent with the rest of the API.

    Args:
        exc: A raised :class:`RollbackError` subclass.

    Returns:
        A :class:`PointlessSQLError` ready to be re-raised.
    """
    if isinstance(exc, RollbackAmbiguous):
        ords = [c.ordinal for c in exc.candidates]
        return ValidationError(
            f"rollback ambiguous: run touched target with ordinals {ords}; "
            "pass op_ordinal to disambiguate"
        )
    if isinstance(exc, RollbackStale):
        return ValidationError(
            f"rollback stale: current_version={exc.current_version} "
            f"expected={exc.expected_version} "
            f"intervening_op_count={exc.intervening_op_count}; "
            "pass allow_force=true to overwrite intervening writes"
        )
    if isinstance(exc, RollbackInvalid):
        return ValidationError(str(exc))
    if isinstance(exc, RollbackTargetNotFound):
        return CatalogNotFoundError(str(exc))
    return exc


def _run_anomaly_chip(request: Request, run_id: str) -> dict[str, Any] | None:
    """Return an anomaly verdict for the run-detail chip, or ``None``.

    Sprint 18.5 — compares the run's reject + errored-op count
    against the global per-day baseline for the same metrics.  If
    either metric breaches the configured σ threshold, returns
    ``{metric, severity, observed, baseline_mean}`` describing the
    worst offender; otherwise ``None`` so the template renders
    nothing.

    Best-effort: any failure logs and returns ``None`` so a broken
    aggregator never breaks the run-detail page.

    Args:
        request: FastAPI request — used for app state.
        run_id: ``AgentRun.id`` whose chip to compute.

    Returns:
        Verdict dict or ``None``.
    """
    try:
        from pointlessql.services import audit_aggregator as agg

        settings = request.app.state.settings
        factory = request.app.state.session_factory
        worst: dict[str, Any] | None = None
        for metric in ("rejects", "errored_ops"):
            result = agg.anomalies(
                factory,
                metric=metric,  # type: ignore[arg-type]
                window_days=settings.audit.anomaly_baseline_window_days,
                sigma=settings.audit.anomaly_threshold_sigma,
                bin_="day",
            )
            if not result["points"]:
                continue
            latest = result["points"][-1]
            if latest["severity"] == "ok":
                continue
            severity_rank = {"warn": 1, "critical": 2}
            if worst is None or severity_rank[latest["severity"]] > severity_rank.get(
                worst["severity"], 0
            ):
                worst = {
                    "metric": metric,
                    "severity": latest["severity"],
                    "observed": latest["observed"],
                    "baseline_mean": latest["baseline_mean"],
                    "sigma": latest["sigma"],
                }
        return worst
    except Exception:  # noqa: BLE001 — chip is best-effort
        return None


@router.get("/runs/{a}/diff/{b}", response_class=HTMLResponse)
async def agent_run_diff_page(
    request: Request,
    a: str,
    b: str,
) -> HTMLResponse:
    """Render the Sprint 18.4 agent-run diff page.

    Loads both runs through
    :func:`pointlessql.api.agent_runs_routes._load_run_summary_bundle`
    + :func:`pointlessql.services.run_diff.build_lineage_diff` so
    the template can show:

    * stat-cards on top (rows touched / value changes / errored
      ops / rejects, with ``+Δ`` chips);
    * an Operations tab with content-aligned op pairs;
    * a Lineage tab with reject-pattern + value-change-volume
      bar charts;
    * a Tool calls tab.

    Args:
        request: FastAPI request.
        a: Left-side run UUID.
        b: Right-side run UUID.

    Returns:
        Rendered ``pages/agent_run_compare.html``.
    """
    # pyright: ignore[reportPrivateUsage] — these helpers
    # intentionally live one module over and are reused by the
    # /runs HTML route to avoid duplicating run-load+summarize SQL.
    from pointlessql.api.agent_runs_routes import (
        _load_run_summary_bundle,  # pyright: ignore[reportPrivateUsage]
        _summarize_run,  # pyright: ignore[reportPrivateUsage]
    )
    from pointlessql.services import run_diff

    factory = request.app.state.session_factory
    run_a, ops_a, tcs_a, qs_a = _load_run_summary_bundle(factory, a)
    run_b, ops_b, tcs_b, qs_b = _load_run_summary_bundle(factory, b)
    summary_a = _summarize_run(run_a, ops_a, tcs_a, qs_a)
    summary_b = _summarize_run(run_b, ops_b, tcs_b, qs_b)
    detail = run_diff.build_detail_diff(
        ops_a=ops_a,
        ops_b=ops_b,
        tool_calls_a=tcs_a,
        tool_calls_b=tcs_b,
        align="content",
    )
    lineage_diff = run_diff.build_lineage_diff(factory, run_a_id=a, run_b_id=b)
    value_changes_a = sum(lineage_diff["value_change_volume_per_table"]["a"].values())
    value_changes_b = sum(lineage_diff["value_change_volume_per_table"]["b"].values())
    rejects_a = sum(lineage_diff["reject_pattern_shift"]["a"].values())
    rejects_b = sum(lineage_diff["reject_pattern_shift"]["b"].values())
    return _templates(request).TemplateResponse(
        request,
        "pages/agent_run_compare.html",
        {
            "run_a": serialize_agent_run(run_a),
            "run_b": serialize_agent_run(run_b),
            "summary_a": summary_a,
            "summary_b": summary_b,
            "value_changes_a": value_changes_a,
            "value_changes_b": value_changes_b,
            "rejects_a": rejects_a,
            "rejects_b": rejects_b,
            "detail": detail,
            "lineage_diff": lineage_diff,
            "rows_touched_diff": summary_b["rows_touched"] - summary_a["rows_touched"],
            "errored_ops_diff": summary_b["errored_ops_count"]
            - summary_a["errored_ops_count"],
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
