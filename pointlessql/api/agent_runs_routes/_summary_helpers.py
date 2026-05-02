"""Summary + run-bundle loaders, shared by the summary, diff, and HTML compare paths.

Two helpers live here:

* :func:`summarize_run` — pure aggregator that produces the Family-B
  risk-summary dict from already-loaded ORM rows.
* :func:`load_run_summary_bundle` — single transaction that loads a
  run plus every per-run sibling (operations, tool calls, query
  history) so the summary aggregator can run without a second
  round-trip.

Both names are re-exported under their original underscore-prefixed
spellings (``_summarize_run`` / ``_load_run_summary_bundle``) by the
package facade because the run-compare HTML route in
:mod:`pointlessql.api.runs_routes.diff` imports them through that
spelling.  Keeping the underscore at the public-facade layer signals
that the contract is intra-repo, not external.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import AgentRunOperation, AgentRunToolCall, QueryHistory
from pointlessql.models.agent_runs import AgentRun


def summarize_run(
    run_row: AgentRun,
    operations: list[AgentRunOperation],
    tool_calls: list[AgentRunToolCall],
    queries: list[QueryHistory],
) -> dict[str, Any]:
    """Produce the Family-B risk-summary payload for one run.

    Pure helper — takes already-loaded ORM rows so the diff route
    can summarise both sides in one DB transaction.

    Args:
        run_row: The ``agent_runs`` row.
        operations: Per-run operation rows.
        tool_calls: Per-run LLM tool-call rows.
        queries: Per-run ``query_history`` rows.

    Returns:
        ``{rows_touched, delta_version_range, errored_ops_count,
        failing_ops, queries_count, tables_touched, status,
        has_denied_reason}``.  ``failing_ops`` is a list of the
        per-op detail rows (op_id, ordinal, op_name, target_table,
        error_message, started_at, finished_at) for every operation
        whose ``error_message`` is non-null so the Incident-Responder
        agent can identify which op failed without a separate
        per-op fetch.  Deliberately omits ``cost_gate_threshold``
        (anti-gaming — agents shouldn't read the threshold they
        could be tuned to stay under).
    """
    tables_touched: list[str] = []
    if run_row.tables_touched:
        try:
            decoded: Any = json.loads(run_row.tables_touched)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            tables_touched = [
                str(item)  # pyright: ignore[reportUnknownArgumentType]
                for item in decoded  # pyright: ignore[reportUnknownVariableType]
            ]
    rows_touched = sum((op.rows_affected or 0) for op in operations)
    errored_ops_count = sum(1 for op in operations if op.error_message)
    failing_ops: list[dict[str, Any]] = [
        {
            "op_id": op.id,
            "ordinal": op.ordinal,
            "op_name": op.op_name,
            "target_table": op.target_table,
            "error_message": op.error_message,
            "started_at": op.started_at.isoformat() if op.started_at else None,
            "finished_at": op.finished_at.isoformat() if op.finished_at else None,
        }
        for op in operations
        if op.error_message
    ]
    delta_version_range: dict[str, list[int | None]] = {}
    for op in operations:
        if op.target_table is None:
            continue
        bounds = delta_version_range.setdefault(
            op.target_table, [op.delta_version_before, op.delta_version_after]
        )
        if op.delta_version_before is not None:
            current_lo = bounds[0]
            if current_lo is None or op.delta_version_before < current_lo:
                bounds[0] = op.delta_version_before
        if op.delta_version_after is not None:
            current_hi = bounds[1]
            if current_hi is None or op.delta_version_after > current_hi:
                bounds[1] = op.delta_version_after
    return {
        "id": run_row.id,
        "status": run_row.status,
        "principal": run_row.principal,
        "agent_id": run_row.agent_id,
        "rows_touched": rows_touched,
        "errored_ops_count": errored_ops_count,
        "failing_ops": failing_ops,
        "operations_count": len(operations),
        "tool_calls_count": len(tool_calls),
        "queries_count": len(queries),
        "tables_touched": tables_touched,
        "delta_version_range": delta_version_range,
        "has_denied_reason": bool(run_row.denied_reason),
        "started_at": run_row.started_at.isoformat() if run_row.started_at else None,
        "finished_at": (run_row.finished_at.isoformat() if run_row.finished_at else None),
    }


def load_run_summary_bundle(
    factory: Any, run_id: str
) -> tuple[AgentRun, list[AgentRunOperation], list[AgentRunToolCall], list[QueryHistory]]:
    """Load run + every per-run sibling needed for ``summarize_run``.

    Args:
        factory: Sessionmaker callable from ``app.state``.
        run_id: UUID of the run to load.

    Returns:
        Tuple of detached ORM rows: run, operations, tool calls,
        query-history.

    Raises:
        CatalogNotFoundError: No agent run with that id.
    """
    with factory() as session:
        run_row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run_row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        operations = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == run_id)
                .order_by(AgentRunOperation.ordinal)
            ).all()
        )
        tool_calls = list(
            session.scalars(
                select(AgentRunToolCall)
                .where(AgentRunToolCall.agent_run_id == run_id)
                .order_by(AgentRunToolCall.called_at)
            ).all()
        )
        queries = list(
            session.scalars(
                select(QueryHistory)
                .where(QueryHistory.agent_run_id == run_id)
                .order_by(QueryHistory.started_at.desc())
            ).all()
        )
        for entity in (run_row, *operations, *tool_calls, *queries):
            session.expunge(entity)
    return run_row, operations, tool_calls, queries
