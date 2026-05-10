"""Per-run data loaders shared across detail, rollback and audit-cross-ref.

Every helper here returns plain dicts (or detached ORM rows) shaped
for direct consumption by the Jinja templates and the JSON sibling
endpoints.  Three names are explicitly cross-imported by
:mod:`pointlessql.api.agent_runs_routes` so it can answer the
``/api/agent-runs/{id}/audit/*`` endpoints without re-implementing
the same SQL: ``load_lineage_summary_for_run``,
``load_rejects_for_run``, ``load_unattributed_for_run``.

``load_operations_for_run`` is also imported by
:mod:`tests.test_runs_op_filter` because it covers the cross-axis
``?op_id=`` filter behaviour, and is re-exported from
:mod:`pointlessql.api.runs_routes.__init__` to keep that import
path stable.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import Request
from sqlalchemy import func, select

from pointlessql.models import (
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
    AuditLog,
    NotebookCellRun,
    NotebookOutput,
    QueryHistory,
    RewriteAttempt,
)
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services import output_rendering as output_rendering_service


def load_runs(
    request: Request,
    *,
    offset: int = 0,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch one page of agent-run rows plus the global count.

    Scoped to the caller's resolved workspace.  The super-admin
    "All workspaces" lens skips the filter via a separate code
    path.

    Args:
        request: Incoming FastAPI request.
        offset: Zero-based offset of the first row in the page.
        limit: Max rows to return; the list page caps at the table
            renderer's natural size.

    Returns:
        ``(rows, total)`` — one dict per row (newest-first, shaped by
        :func:`serialize_agent_run`) plus the unfiltered ``COUNT(*)``
        so the caller can decide whether to render a Load-More CTA.
    """
    from pointlessql.api.agent_runs_routes import serialize_agent_run

    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    with factory() as session:
        total = int(
            session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.workspace_id == workspace_id)
            )
            or 0
        )
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 1))
        )
        rows = list(session.scalars(stmt).all())
        return [serialize_agent_run(row) for row in rows], total


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


def load_audit_entries_for_run(
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
    """Aggregate ``lineage_row_edges`` per operation.

    Joins ``lineage_row_edges`` against ``agent_run_operations`` so
    the run-detail Lineage tab can render one row per op with
    source/target FQNs, op name, and edge count.  Operations with no
    recorded edges are excluded (the empty-state alert covers that).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id:  cross-axis filter — when set, restrict
            the aggregate to a single op.

    Returns:
        Dict shaped ``{"total_edges": int, "rows": [{
        "ordinal": int, "op_name": str, "source_table": str,
        "target_table": str, "edge_count": int,
        "sample_target_row_id": str | None}, ...]}`` ready to
        feed the run-detail Lineage tab.  ``sample_target_row_id``
        is an arbitrary representative row id for the (op, target)
        group — used by the Lineage sub-pills to deep-link a
        "Trace target row" click into the Row-trace pane.
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
                func.min(LineageRowEdge.target_row_id).label("sample_target_row_id"),
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
                    "sample_target_row_id": row[6],
                }
            )
    return {"total_edges": total, "rows": rows}


def load_rejects_for_run(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return ``lineage_row_rejects`` for the run-detail tab.

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id:  cross-axis filter — when set, restrict
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


async def load_uc_mutations_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return soyuz audit-log rows attributed to *run_id*.

    Asks soyuz's ``GET /audit-log?agent_run_id=`` cross-reference
    surface.  Returns ``[]`` against older soyuz versions that lack
    the endpoint — the run-detail "UC mutations" tab simply renders
    empty.

    Args:
        request: Incoming FastAPI request — provides
            ``app.state.uc_client``.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Raw soyuz JSON dicts (``id`` / ``action`` / ``target`` /
        ``principal`` / ``agent_run_id`` / ``client_ip`` /
        ``detail`` / ``created_at``) ready for the template.
    """
    from pointlessql.services.audit import _soyuz as soyuz_audit

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


def load_operations_for_run(
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
        op_id:  cross-axis filter — when set, only the
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
            # bare-broad-ok: column-edge badge renders 0 on metadata-DB hiccup
            column_edge_counts = {}
        try:
            from pointlessql.services.lineage_edges import count_value_changes_for_op

            value_change_counts = count_value_changes_for_op(factory, op_ids)
        except Exception:  # noqa: BLE001 — best-effort badge population
            # bare-broad-ok: value-change badge renders 0 on metadata-DB hiccup
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
        warnings: list[str] | None = None
        if row.warnings_json:
            try:
                parsed_warnings = json.loads(row.warnings_json)
                if isinstance(parsed_warnings, dict):
                    raw = parsed_warnings.get("markers")
                    if isinstance(raw, list):
                        warnings = [str(m) for m in raw]
            except json.JSONDecodeError:
                warnings = None
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
                "warnings": warnings,
                "column_edges_count": column_edge_counts.get(row.id, 0),
                "value_changes_count": value_change_counts.get(row.id, 0),
                "training_params": training_params,
                "env_snapshot": env_snapshot,
            }
        )
    return out


def load_source_for_run(
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


def load_events_for_run(
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


def load_queries_for_run(
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


def load_tool_calls_for_run(
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


def load_rewrite_attempts_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ``rewrite_attempts`` rows for *run_id*, oldest first.

    Surfaces the Phase-39 explain-first rewrite-loop trace in the
    Operations top-tab's "Rewrites" sub-pane.  Rows are ordered by
    ``attempt_no`` ASC so the loop reads top-to-bottom in submission
    order.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts with ``attempt_no``, ``verdict``, hashes, costs,
        cost-delta (when both costs are set), reason, and an ISO
        ``created_at`` timestamp.
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(RewriteAttempt)
            .where(RewriteAttempt.agent_run_id == run_id)
            .order_by(RewriteAttempt.attempt_no)
        )
        for row in session.scalars(stmt).all():
            cost_delta: int | None
            if row.rewritten_cost is not None:
                cost_delta = int(row.original_cost) - int(row.rewritten_cost)
            else:
                cost_delta = None
            out.append(
                {
                    "attempt_no": row.attempt_no,
                    "verdict": row.verdict,
                    "original_sql_hash": row.original_sql_hash,
                    "rewritten_sql_hash": row.rewritten_sql_hash,
                    "original_cost": int(row.original_cost),
                    "rewritten_cost": (
                        int(row.rewritten_cost) if row.rewritten_cost is not None else None
                    ),
                    "cost_delta": cost_delta,
                    "reason": row.reason,
                    "created_at": (row.created_at.isoformat() if row.created_at else None),
                }
            )
    return out
