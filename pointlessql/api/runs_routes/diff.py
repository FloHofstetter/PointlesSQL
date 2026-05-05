"""Side-by-side agent-run comparison page.

Renders ``pages/agent_run_compare.html`` with stat cards, a content-
aligned operations diff, a lineage diff (reject patterns + value-
change volume), and the tool-call timeline.  Reuses the per-run
summary helpers from :mod:`pointlessql.api.agent_runs_routes` so
both the list-page sibling and the diff page share the same SQL.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.runs_routes._shared import templates

router = APIRouter()


@router.get("/runs/{a}/diff/{b}", response_class=HTMLResponse)
async def agent_run_diff_page(
    request: Request,
    a: str,
    b: str,
) -> HTMLResponse:
    """Render the agent-run diff page.

    Loads both runs through
    :func:`pointlessql.api.agent_runs_routes._load_run_summary_bundle`
    + :func:`pointlessql.services.run_diff.build_lineage_diff` so the
    template can show stat cards, an Operations tab with content-
    aligned op pairs, a Lineage tab with reject-pattern + value-
    change-volume bar charts, and a Tool calls tab.

    Args:
        request: FastAPI request.
        a: Left-side run UUID.
        b: Right-side run UUID.

    Returns:
        Rendered ``pages/agent_run_compare.html``.
    """
    # The two summary helpers intentionally live in agent_runs_routes
    # and are reused here to avoid duplicating run-load+summarize SQL.
    from pointlessql.api.agent_runs_routes import (
        _load_run_summary_bundle,  # pyright: ignore[reportPrivateUsage]
        _summarize_run,  # pyright: ignore[reportPrivateUsage]
        serialize_agent_run,
    )
    from pointlessql.services import run_diff

    factory = request.app.state.session_factory
    run_a, ops_a, tcs_a, qs_a = _load_run_summary_bundle(factory, a)
    run_b, ops_b, tcs_b, qs_b = _load_run_summary_bundle(factory, b)
    summary_a = _summarize_run(run_a, ops_a, tcs_a, qs_a)
    summary_b = _summarize_run(run_b, ops_b, tcs_b, qs_b)
    from pointlessql.api.dependencies import get_user

    detail = run_diff.build_detail_diff(
        ops_a=ops_a,
        ops_b=ops_b,
        tool_calls_a=tcs_a,
        tool_calls_b=tcs_b,
        align="content",
    )
    lineage_diff = run_diff.build_lineage_diff(factory, run_a_id=a, run_b_id=b)
    # Phase 18.9 — cell-level + column-lineage edge diff.  Cleartext
    # cells require admin; everyone else sees masked placeholders.
    reveal = bool(get_user(request).get("is_admin"))
    value_changes_diff = run_diff.build_value_changes_diff(
        factory, run_a_id=a, run_b_id=b, reveal=reveal
    )
    column_lineage_diff = run_diff.build_column_lineage_diff(factory, run_a_id=a, run_b_id=b)
    value_changes_a = sum(lineage_diff["value_change_volume_per_table"]["a"].values())
    value_changes_b = sum(lineage_diff["value_change_volume_per_table"]["b"].values())
    rejects_a = sum(lineage_diff["reject_pattern_shift"]["a"].values())
    rejects_b = sum(lineage_diff["reject_pattern_shift"]["b"].values())
    return templates(request).TemplateResponse(
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
            "value_changes_diff": value_changes_diff,
            "column_lineage_diff": column_lineage_diff,
            "rows_touched_diff": summary_b["rows_touched"] - summary_a["rows_touched"],
            "errored_ops_diff": summary_b["errored_ops_count"] - summary_a["errored_ops_count"],
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
