"""Per-run risk-summary + side-by-side run diff endpoints.

Two supervisor-scope reads:

* ``GET /api/agent-runs/{run_id}/summary`` — Family-B risk summary.
* ``GET /api/agent-runs/diff`` — side-by-side diff of two runs with
  optional op + lineage detail.

The summary helpers (``summarize_run`` and ``load_run_summary_bundle``)
live in :mod:`._summary_helpers` and are re-exported under their
underscore-prefixed legacy names by the package facade for the
HTML run-compare route in :mod:`pointlessql.api.runs_routes.diff`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.agent_runs_routes._summary_helpers import (
    load_run_summary_bundle,
    summarize_run,
)
from pointlessql.api.dependencies import get_user, require_supervisor
from pointlessql.services.run_diff import (
    AlignmentMode,
    build_column_lineage_diff,
    build_detail_diff,
    build_lineage_diff,
    build_value_changes_diff,
)

router = APIRouter()


@router.get("/api/agent-runs/{run_id}/summary")
async def api_agent_run_summary(request: Request, run_id: str) -> dict[str, Any]:
    """Risk-summary JSON for one run.  Supervisor scope required.

    Backs the ``pql_run_summary`` Hermes tool and is the per-side
    payload of the diff route below.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string from the URL.

    Returns:
        Dict shaped by :func:`summarize_run`.
        :func:`require_supervisor` raises :class:`AuthorizationError`
        when the caller lacks the ``supervisor`` scope, and
        :func:`load_run_summary_bundle` raises
        :class:`CatalogNotFoundError` when the run id is unknown.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    run_row, operations, tool_calls, queries = load_run_summary_bundle(factory, run_id)
    return summarize_run(run_row, operations, tool_calls, queries)


@router.get("/api/agent-runs/diff")
async def api_agent_runs_diff(
    request: Request,
    a: str = Query(..., description="UUID of run A"),
    b: str = Query(..., description="UUID of run B"),
    detail: bool = Query(default=False),
    align: str = Query(default="ordinal", pattern="^(ordinal|content)$"),
) -> dict[str, Any]:
    """Diff between two runs.  Supervisor scope required.

    The base response is a side-by-side summary diff; passing
    ``detail=true`` extends it with an op-by-op + tool-call-by-
    tool-call diff (see
    :func:`pointlessql.services.run_diff.build_detail_diff` for
    the alignment strategies).

    Args:
        request: Incoming FastAPI request.
        a: Run UUID for the left side of the comparison.
        b: Run UUID for the right side.
        detail: When ``True``, the response also carries
            ``operations_diff`` + ``tool_calls_diff``.
        align: ``"ordinal"`` (default — pair by index) or
            ``"content"`` (greedy match on op_name/target_table).

    Returns:
        Always ``{a_summary, b_summary, ops_count_diff,
        tool_calls_count_diff, queries_count_diff, rows_touched_diff,
        errored_ops_diff, tables_only_in_a, tables_only_in_b,
        tables_in_both, status_diff}``.  When ``detail=True`` adds
        ``operations_diff``, ``tool_calls_diff``, ``align``,
        ``truncated``, ``lineage_diff`` (volume),
        ``value_changes_diff`` (cell-level, PII-masked unless
        admin) and ``column_lineage_diff`` (edge-level
        only-in-a / only-in-b / changed buckets).

        :func:`require_supervisor` raises :class:`AuthorizationError`
        when the caller lacks the ``supervisor`` scope;
        :func:`load_run_summary_bundle` raises
        :class:`CatalogNotFoundError` when either run id is unknown.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    run_a, ops_a, tcs_a, qs_a = load_run_summary_bundle(factory, a)
    run_b, ops_b, tcs_b, qs_b = load_run_summary_bundle(factory, b)
    summary_a = summarize_run(run_a, ops_a, tcs_a, qs_a)
    summary_b = summarize_run(run_b, ops_b, tcs_b, qs_b)
    tables_a = set(summary_a["tables_touched"])
    tables_b = set(summary_b["tables_touched"])
    payload: dict[str, Any] = {
        "a_summary": summary_a,
        "b_summary": summary_b,
        "ops_count_diff": summary_b["operations_count"] - summary_a["operations_count"],
        "tool_calls_count_diff": summary_b["tool_calls_count"] - summary_a["tool_calls_count"],
        "queries_count_diff": summary_b["queries_count"] - summary_a["queries_count"],
        "rows_touched_diff": summary_b["rows_touched"] - summary_a["rows_touched"],
        "errored_ops_diff": summary_b["errored_ops_count"] - summary_a["errored_ops_count"],
        "tables_only_in_a": sorted(tables_a - tables_b),
        "tables_only_in_b": sorted(tables_b - tables_a),
        "tables_in_both": sorted(tables_a & tables_b),
        "status_diff": {"a": summary_a["status"], "b": summary_b["status"]},
    }
    if detail:
        # FastAPI Query(pattern=…) already constrains align; cast
        # to the typed alias for the service signature.
        align_mode: AlignmentMode = "content" if align == "content" else "ordinal"
        payload.update(
            build_detail_diff(
                ops_a=ops_a,
                ops_b=ops_b,
                tool_calls_a=tcs_a,
                tool_calls_b=tcs_b,
                align=align_mode,
            )
        )
        payload["lineage_diff"] = build_lineage_diff(
            factory,
            run_a_id=a,
            run_b_id=b,
        )
        # Cell-level value diff + column-lineage edge diff.  Cleartext
        # cells require admin; auditor-scope callers see masked
        # placeholders even on the diff route, mirroring the
        # /audit/value-changes contract.
        user = get_user(request)
        reveal = bool(user.get("is_admin"))
        payload["value_changes_diff"] = build_value_changes_diff(
            factory,
            run_a_id=a,
            run_b_id=b,
            reveal=reveal,
        )
        payload["column_lineage_diff"] = build_column_lineage_diff(
            factory,
            run_a_id=a,
            run_b_id=b,
        )
    return payload
