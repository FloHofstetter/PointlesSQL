"""On-demand ``dbt`` invocation endpoints.

Three POST routes — ``/api/dbt/run``, ``/api/dbt/test``,
``/api/dbt/compile`` — plus an admin-only ``/api/dbt/deps`` for
package installs, and four read-only accessors over the manifest
(``/api/dbt/manifest``, ``/api/dbt/coverage``, ``/api/dbt/test-failures``,
``/api/dbt/runs``).  All three writes (``run`` / ``test`` / ``deps``)
require supervisor scope; ``compile`` only needs an authenticated
user because it does not mutate state.

The handlers wrap a :class:`pointlessql.services.dbt._executor.DBTExecutor`
invocation, then hand the result files to the bridge in
:mod:`pointlessql.services.dbt._bridge` so each executed model + test
lands as one ``agent_run_operations`` row.

Lifecycle: callers may pass an ``agent_run_id`` they have already
registered (the typical agent path).  When absent, the route
auto-creates an :class:`AgentRun` keyed to the calling user's email
so the audit trail is never headless.  We finish the run only when
we created it ourselves; caller-managed runs get to decide their
own terminal state.

lifted the 1061-LOC helper body into sibling modules
under ``pointlessql/api/dbt/`` — this file now holds only the
route handlers themselves.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dbt._executor import executor as build_executor
from pointlessql.api.dbt._lifecycle import result_payload
from pointlessql.api.dbt._run_test import load_manifest_or_404, run_or_test
from pointlessql.api.dependencies import (
    PaginationParams,
    get_user,
    pagination,
    require_admin,
    require_supervisor,
)
from pointlessql.exceptions import AuthenticationError
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.lineage import LineageRowReject
from pointlessql.services.dbt import as_dict, project_models

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dbt"])


@router.post("/api/dbt/compile")
async def api_dbt_compile(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Run ``dbt compile`` against the project.

    Read-only — refreshes the manifest without writing data.  Any
    authenticated user can call it.

    Args:
        request: Incoming FastAPI request.
        body: Optional ``{"models": ["foo", "bar"]}`` ``--select``
            filter.

    Returns:
        JSON envelope with executor result + (empty) bridge summary.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
            ``DBTExecutionError`` (503 when the dbt CLI cannot be
            spawned) is rendered by the centralised handler — no
            inline raise.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("auth required")

    models = body.get("models") if isinstance(body.get("models"), list) else None
    executor = build_executor(request)
    # DBTExecutionError is a PointlessSQLError(503); the centralised
    # handler renders it directly — no inline translation required.
    result = await executor.compile(models=models)
    return result_payload(result, agent_run_id=None)


@router.post("/api/dbt/deps")
async def api_dbt_deps(
    request: Request,
) -> dict[str, Any]:
    """Run ``dbt deps`` to install packages from ``packages.yml``.

    Admin-only because it mutates the project's ``dbt_packages/``
    directory and can pull arbitrary git repositories.

    Args:
        request: Incoming FastAPI request.

    Returns:
        JSON envelope with executor result.
    """
    require_admin(request)
    executor = build_executor(request)
    # DBTExecutionError is a PointlessSQLError(503); centralised
    # handler renders it directly.
    result = await executor.deps()
    await audit(request, "dbt_deps", "dbt:deps", {"exit_code": result.exit_code})
    return result_payload(result, agent_run_id=None)


@router.post("/api/dbt/run")
async def api_dbt_run(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Run ``dbt run`` to materialise models, with audit emit.

    Args:
        request: Incoming FastAPI request.
        body: Optional ``{"models": [...], "full_refresh": bool,
            "agent_run_id": str}``.

    Returns:
        JSON envelope with executor result + per-node summary.
    """
    return await run_or_test(request, body=body, op_kind="run")


@router.post("/api/dbt/test")
async def api_dbt_test(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Run ``dbt test`` to evaluate test definitions, with audit emit.

    Args:
        request: Incoming FastAPI request.
        body: Optional ``{"models": [...], "agent_run_id": str}``.

    Returns:
        JSON envelope with executor result + per-test summary.
    """
    return await run_or_test(request, body=body, op_kind="test")


@router.get("/api/dbt/manifest")
async def api_dbt_manifest(request: Request) -> dict[str, Any]:
    """Return the model + test summary from ``target/manifest.json``.

    Read-only.  Available to any authenticated user — the manifest
    only carries SQL source + dependency metadata, no row data.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"manifest_generated_at": str | None, "models": [...]}``
        with one entry per model.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
            ``ResourceNotFoundError`` (404 no manifest) and
            ``EngineError`` (500 corrupted) propagate from
            :func:`load_manifest_or_404`.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("auth required")
    manifest = load_manifest_or_404(request)
    metadata = as_dict(manifest.get("metadata"))
    generated_at = metadata.get("generated_at")
    return {
        "manifest_generated_at": str(generated_at) if generated_at else None,
        "models": project_models(manifest),
    }


@router.get("/api/dbt/coverage")
async def api_dbt_coverage(request: Request) -> dict[str, Any]:
    """Return the test-coverage ratio for the dbt project.

    Coverage is the share of models that have ≥1 test defined.  Drives
    a cockpit metric in 36.4 (UI) and an agent self-check in 36.B
    plugin tools.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"models_total": int, "models_with_tests": int,
        "ratio": float, "untested": list[str]}``.  ``ratio`` is
        ``0.0`` when there are no models (avoids a zero-division
        500).

    Raises:
        AuthenticationError: 401 when the request is anonymous.
            ``ResourceNotFoundError`` (404 no manifest) propagates
            from :func:`load_manifest_or_404`.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("auth required")
    manifest = load_manifest_or_404(request)
    models = project_models(manifest)
    total = len(models)
    with_tests = sum(1 for m in models if m["tests"])
    untested = [str(m["unique_id"]) for m in models if not m["tests"]]
    ratio = (with_tests / total) if total else 0.0
    return {
        "models_total": total,
        "models_with_tests": with_tests,
        "ratio": round(ratio, 4),
        "untested": untested,
    }


@router.get("/api/dbt/test-failures")
async def api_dbt_test_failures(
    request: Request,
    agent_run_id: str | None = Query(
        default=None,
        description=(
            "agent_runs.id whose failures to list; omit for recent failures across all dbt runs"
        ),
    ),
    paging: PaginationParams = Depends(pagination),
) -> dict[str, Any]:
    """Return the dbt-test failures for one agent run.

    Joins ``lineage_row_rejects`` (where ``reason='expectation_failed'``)
    with ``agent_run_operations`` so each row carries the failing
    test's ``unique_id``, the model relation it ran against, dbt's
    failure message, and the owning op id for cross-link.

    Supervisor or auditor scope required: per-run audit-axis routes
    follow the same asymmetric ladder as the rest of
    ``/api/agent-runs/{id}/audit/*``.  Callers lacking that scope
    get the :class:`HTTPException` (403) propagated from
    :func:`require_supervisor`.

    Args:
        request: Incoming FastAPI request.
        agent_run_id: UUID of the run whose failures to list.  When
            omitted, returns recent failures across every dbt-cli
            run for the cockpit's "Test failures" tab.
        paging: Shared offset+limit pair (default page size 100, max 1000).

    Returns:
        ``{"agent_run_id": str | None, "row_count": int, "rows": [...]}``.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        if agent_run_id is not None:
            stmt = (
                select(LineageRowReject, AgentRunOperation)
                .join(AgentRunOperation, AgentRunOperation.id == LineageRowReject.op_id)
                .where(LineageRowReject.run_id == agent_run_id)
                .where(LineageRowReject.reason == "expectation_failed")
                .order_by(LineageRowReject.id.asc())
                .offset(paging.offset)
                .limit(paging.limit)
            )
        else:
            stmt = (
                select(LineageRowReject, AgentRunOperation)
                .join(AgentRunOperation, AgentRunOperation.id == LineageRowReject.op_id)
                .join(AgentRun, AgentRun.id == LineageRowReject.run_id)
                .where(LineageRowReject.reason == "expectation_failed")
                .where(AgentRun.agent_id == "dbt-cli")
                .order_by(LineageRowReject.id.desc())
                .offset(paging.offset)
                .limit(paging.limit)
            )
        for reject, op in session.execute(stmt).all():
            params: dict[str, Any] = {}
            if op.params_json:
                try:
                    import json as _json

                    params = as_dict(_json.loads(op.params_json))
                except ValueError, TypeError:
                    params = {}
            severity = params.get("severity") or "error"
            rows.append(
                {
                    "test_unique_id": reject.source_row_id,
                    "model_relation": op.target_table,
                    "severity": str(severity),
                    "message": reject.detail,
                    "op_id": op.id,
                    "agent_run_id": reject.run_id,
                    "rejected_at": reject.created_at.isoformat() if reject.created_at else None,
                },
            )
    return {
        "agent_run_id": agent_run_id,
        "row_count": len(rows),
        "rows": rows,
    }


@router.get("/api/dbt/runs")
async def api_dbt_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    """Return recent dbt-cli :class:`AgentRun` rows.

    Drives the dbt cockpit's Recent-runs sub-tab.  Filters
    ``AgentRun`` by ``agent_id == 'dbt-cli'`` (the value
    :func:`create_owned_run` writes for auto-spawned dbt runs)
    and orders newest-first.  Bypassing /api/runs avoids the
    workspace-cap of 200 unrelated runs drowning out the dbt
    timeline.

    Args:
        request: Incoming FastAPI request.
        limit: Hard row cap (1–200, default 20).

    Returns:
        ``{"row_count": int, "runs": [{...}, ...]}``.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("auth required")
    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    runs: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .where(AgentRun.agent_id == "dbt-cli")
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
        )
        for row in session.scalars(stmt).all():
            runs.append(
                {
                    "id": row.id,
                    "principal": row.principal,
                    "notebook_path": row.notebook_path,
                    "status": row.status,
                    "exit_code": row.exit_code,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                },
            )
    return {"row_count": len(runs), "runs": runs}
