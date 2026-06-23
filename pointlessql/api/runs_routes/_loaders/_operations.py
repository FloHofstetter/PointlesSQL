"""Op-trace axis — operations, tool calls, rewrite attempts, query history."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.models import (
    AgentRunOperation,
    AgentRunToolCall,
    QueryHistory,
    RewriteAttempt,
)


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


def load_rewrite_attempts_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ``rewrite_attempts`` rows for *run_id*, oldest first.

    Surfaces the explain-first rewrite-loop trace in the
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
