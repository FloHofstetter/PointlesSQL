"""Per-run supervision view — HTML page + JSON sibling.

Two HTTP-facing endpoints:

* ``GET /runs/{run_id}`` — full HTML supervision card deck with
  cells, outputs, audit trail, operations, conformance findings,
  unattributed writes, lineage summary, rejects, and the rollback
  dropdown.  Optional ``?op_id=`` query param deep-links into a
  single op across every cross-axis tab.
* ``GET /api/agent-runs/{run_id}/full`` — JSON sibling that backs
  the ``pql_my_run`` Hermes tool.

Two single-axis helpers live alongside the routes here because they
are nowhere else imported: ``_conformance_findings_for_run`` (passive
soyuz check) and ``_run_anomaly_chip`` (best-effort baseline
comparison).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_uc_client
from pointlessql.api.runs_routes._loaders import (
    load_audit_entries_for_run,
    load_cell_runs_for_run,
    load_events_for_run,
    load_lineage_summary_for_run,
    load_operations_for_run,
    load_outputs_for_run,
    load_queries_for_run,
    load_rejects_for_run,
    load_source_for_run,
    load_tool_calls_for_run,
    load_uc_mutations_for_run,
    load_unattributed_for_run,
)
from pointlessql.api.runs_routes._shared import load_run, templates
from pointlessql.api.runs_routes.rollback import rollback_targets_for_run
from pointlessql.conventions import load_conventions
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import output_rendering as output_rendering_service
from pointlessql.services.conformance import (
    ConformanceFinding,
    check_table_against_layer,
    infer_layer_from_full_name,
)
from pointlessql.settings import Settings

router = APIRouter()


@router.get("/api/agent-runs/{run_id}/full")
async def api_agent_run_full(request: Request, run_id: str) -> dict[str, Any]:
    """Return the full supervision payload for *run_id* in one round-trip.

    Backs the ``pql_my_run`` Hermes tool.  Joins the serialised
    :class:`AgentRun` row with every per-run sibling table the
    supervision view already aggregates: source bytes, operations,
    tool-call trail, lifecycle events, attributed query history.

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
        :func:`load_run` raises :class:`CatalogNotFoundError` when
        no row with that id exists; FastAPI's exception handlers
        translate that into a 404 response.
    """
    from pointlessql.api.agent_runs_routes import serialize_agent_run

    run_row = load_run(request, run_id)
    return {
        "run": serialize_agent_run(run_row),
        "source": load_source_for_run(request, run_id),
        "operations": load_operations_for_run(request, run_id),
        "tool_calls": load_tool_calls_for_run(request, run_id),
        "events": load_events_for_run(request, run_id),
        "queries": load_queries_for_run(request, run_id),
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


def _run_anomaly_chip(request: Request, run_id: str) -> dict[str, Any] | None:
    """Return an anomaly verdict for the run-detail chip, or ``None``.

    Compares the run's reject + errored-op count against the global
    per-day baseline for the same metrics.  If either metric breaches
    the configured σ threshold, returns ``{metric, severity,
    observed, baseline_mean}`` describing the worst offender;
    otherwise ``None`` so the template renders nothing.

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
        op_id:  cross-axis deep-link.  When set, every
            tab whose surface has an ``op_id`` linkage (Operations,
            Rejects, Lineage) renders pre-filtered to this single
            op; tabs without that linkage render unfiltered with a
            visible "(filter inactive on this surface)" hint.

    Returns:
        ``pages/run_view.html`` with ``run``, ``cells``,
        ``cell_outputs``, ``cell_runs``, ``tool_calls``, and the
        ``render_markdown`` helper in context.
    """
    from pointlessql.api.agent_runs_routes import serialize_agent_run

    run_row = load_run(request, run_id)
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

    # ``filter_op_ordinal`` is the human-friendly label rendered in
    # the cross-axis chip; the deep link carries the integer id.
    filter_op_ordinal: int | None = None
    if op_id is not None:
        ops_for_label = load_operations_for_run(request, run_id, op_id=op_id)
        if ops_for_label:
            filter_op_ordinal = int(ops_for_label[0]["ordinal"])
        else:
            # Stale link (op deleted, run rerun, ...) — fall back to
            # unfiltered view rather than 404; cockpit drill-downs
            # should be permissive.
            op_id = None

    # run-detail anomaly chip.  Best-effort: if the
    # aggregator fails the run still renders without the chip.
    run_anomaly: dict[str, Any] | None = _run_anomaly_chip(request, run_id)

    return templates(request).TemplateResponse(
        request,
        "pages/run_view.html",
        {
            "notebook_path": run_row.notebook_path,
            "cells": cells,
            "cell_outputs": load_outputs_for_run(request, run_id),
            "cell_runs": load_cell_runs_for_run(request, run_id),
            "audit_entries": load_audit_entries_for_run(request, run_id),
            "operations": load_operations_for_run(request, run_id, op_id=op_id),
            "source": load_source_for_run(request, run_id),
            "events": load_events_for_run(request, run_id),
            "queries": load_queries_for_run(request, run_id),
            "tool_calls": load_tool_calls_for_run(request, run_id),
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
            "uc_mutations": await load_uc_mutations_for_run(request, run_id),
            "lineage_summary": load_lineage_summary_for_run(request, run_id, op_id=op_id),
            "rejects": load_rejects_for_run(request, run_id, op_id=op_id),
            "rollback_targets": rollback_targets_for_run(request, run_id),
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
