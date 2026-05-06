"""On-demand ``dbt`` invocation endpoints.

Three POST routes — ``/api/dbt/run``, ``/api/dbt/test``,
``/api/dbt/compile`` — plus an admin-only ``/api/dbt/deps`` for
package installs.  All three writes (``run`` / ``test`` / ``deps``)
require supervisor scope; ``compile`` only needs an authenticated
user because it does not mutate state.

The handlers wrap a :class:`pointlessql.services.dbt_executor.DBTExecutor`
invocation, then hand the result files to the bridge in
:mod:`pointlessql.services.dbt_bridge` so each executed model + test
lands as one ``agent_run_operations`` row.

Lifecycle: callers may pass an ``agent_run_id`` they have already
registered (the typical agent path).  When absent, the route
auto-creates an :class:`AgentRun` keyed to the calling user's email
so the audit trail is never headless.  We finish the run only when
we created it ourselves; caller-managed runs get to decide their
own terminal state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin, require_supervisor
from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models.agent_run_audit import AgentRunOperation
from pointlessql.models.agent_runs import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    AgentRun,
)
from pointlessql.models.lineage import LineageRowReject
from pointlessql.services.dbt_bridge import (
    DBTNodeResult,
    as_dict,
    emit_operations_for_dbt_run,
    emit_test_failure_rejects,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
    project_models,
    summarise,
)
from pointlessql.services.dbt_executor import DBTExecutionError, DBTExecutor, DBTRunResult
from pointlessql.services.governance_events import (
    EVENT_TYPE_DBT_RUN_COMPLETED,
    EVENT_TYPE_DBT_TEST_FAILED,
    EVENT_TYPE_DBT_TEST_WARNED,
    emit_governance_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dbt"])


def _executor(request: Request) -> DBTExecutor:
    """Build a :class:`DBTExecutor` bound to the request's settings."""
    settings = request.app.state.settings
    return DBTExecutor(settings.dbt)


def _create_owned_run(request: Request, user_email: str) -> str:
    """Auto-create an :class:`AgentRun` keyed to the calling user.

    Used when the caller did not supply an ``agent_run_id`` — we still
    want every dbt operation to land under a known parent so the
    cockpit can render the per-run timeline.

    Args:
        request: Incoming request (provides session + workspace).
        user_email: Calling user's email; recorded as ``principal``.

    Returns:
        The newly-minted run id.
    """
    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    with factory() as session:
        row = AgentRun(
            id=run_id,
            workspace_id=workspace_id,
            principal=user_email,
            agent_id="dbt-cli",
            notebook_path="dbt:run",
            source_snapshot_sha=None,
            status=STATUS_RUNNING,
            started_at=started_at,
        )
        session.add(row)
        session.commit()
    return run_id


def _finish_owned_run(
    request: Request,
    run_id: str,
    *,
    succeeded: bool,
    exit_code: int,
) -> None:
    """Mark an auto-created run terminal.

    Args:
        request: Incoming request (provides session).
        run_id: The auto-created run id.
        succeeded: True if no node failed, else False.
        exit_code: dbt's process exit code, recorded on the row.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            return
        row.status = STATUS_SUCCEEDED if succeeded else STATUS_FAILED
        row.finished_at = datetime.now(UTC)
        row.exit_code = exit_code
        session.commit()


def _result_payload(result: DBTRunResult, agent_run_id: str | None) -> dict[str, Any]:
    """Common envelope for the executor's CLI outcome.

    Args:
        result: Executor outcome.
        agent_run_id: The audited run id (``None`` for compile/deps).

    Returns:
        JSON-shaped dict with stable field names.
    """
    return {
        "agent_run_id": agent_run_id,
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": result.duration_seconds,
        "truncated_stdout": result.truncated_stdout,
        "truncated_stderr": result.truncated_stderr,
        "manifest_path": str(result.manifest_path),
        "run_results_path": str(result.run_results_path),
    }


def _classify_severity(nodes: list[DBTNodeResult]) -> tuple[int, int]:
    """Return ``(error_failures, warn_failures)`` from a node list.

    A *failure* is a test (``resource_type='test'``) or model
    (``resource_type='model'``) with ``status='fail'`` or
    ``'error'``.  Tests with ``severity='warn'`` count as warn-
    failures even when their status says ``fail`` — dbt records
    every test that returned > 0 rows as ``status='fail'`` and
    leaves the *consequence* to the consumer (us).

    Args:
        nodes: Per-node results.

    Returns:
        Tuple of (error-severity failure count, warn-severity
        failure count).
    """
    err = 0
    warn = 0
    for n in nodes:
        is_failure = n.status in {"error", "fail"}
        if not is_failure:
            continue
        if n.severity == "warn":
            warn += 1
        else:
            err += 1
    return err, warn


async def _emit_dbt_events(
    request: Request,
    *,
    agent_run_id: str,
    op_kind: str,
    result: DBTRunResult,
    nodes: list[DBTNodeResult],
    err_failures: int,
    warn_failures: int,
) -> None:
    """Fire the per-run + per-test CloudEvents.

    One ``run.completed`` always; one ``test.failed`` per error-
    severity failing test and one ``test.warned`` per warn-severity
    failing test.  Emits sequentially so a flaky sink doesn't break
    the audit trail.

    Args:
        request: Incoming request (for settings + session factory +
            workspace).
        agent_run_id: The owning AgentRun id.
        op_kind: ``"run"`` or ``"test"`` for the run.completed payload.
        result: Executor outcome.
        nodes: Per-node results.
        err_failures: Count of error-severity failures.
        warn_failures: Count of warn-severity failures.
    """
    settings = request.app.state.settings
    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    common: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "op_kind": op_kind,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "err_failures": err_failures,
        "warn_failures": warn_failures,
    }
    await emit_governance_event(
        EVENT_TYPE_DBT_RUN_COMPLETED,
        common,
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    for node in nodes:
        if node.status not in {"error", "fail"}:
            continue
        if node.resource_type != "test":
            continue
        event_type = (
            EVENT_TYPE_DBT_TEST_WARNED if node.severity == "warn" else EVENT_TYPE_DBT_TEST_FAILED
        )
        payload = {
            "agent_run_id": agent_run_id,
            "unique_id": node.unique_id,
            "relation_name": node.relation_name,
            "severity": node.severity,
            "message": node.message,
            "depends_on": node.depends_on,
        }
        await emit_governance_event(
            event_type,
            payload,
            settings=settings,
            session_factory=factory,
            workspace_id=workspace_id,
        )


async def _emit_audit_for_run(
    request: Request,
    *,
    agent_run_id: str,
    result: DBTRunResult,
) -> dict[str, Any]:
    """Parse manifest + run_results and emit ``agent_run_operations`` rows.

    Args:
        request: Incoming request (for the session factory).
        agent_run_id: Owning run id.
        result: Executor outcome with manifest + run_results paths.

    Returns:
        Summary dict with counts and per-node payload (used by the
        callers to build their HTTP response).

    Raises:
        HTTPException: 500 when the bridge cannot emit operation rows.
    """
    if not result.run_results_path.is_file():
        # Compile failure → no run_results.json on disk.  Nothing to
        # emit — the caller still gets the executor envelope so a
        # reviewer can read stderr.
        return {"nodes": [], "ok": 0, "fail": 0, "warn": 0, "skipped": 0}

    try:
        manifest = parse_manifest(result.manifest_path)
        results = parse_run_results(result.run_results_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "dbt bridge could not parse artefacts for run %s: %s",
            agent_run_id,
            exc,
        )
        return {"nodes": [], "ok": 0, "fail": 0, "warn": 0, "skipped": 0}

    nodes = merge_manifest_and_results(manifest, results)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    try:
        op_ids = emit_operations_for_dbt_run(
            factory,
            agent_run_id=agent_run_id,
            nodes=nodes,
            started_at=started_at,
        )
    except AuditUnavailableError as exc:
        logger.error("dbt bridge failed to emit operations: %s", exc)
        raise HTTPException(status_code=500, detail=f"audit emit failed: {exc}") from exc

    rejects_inserted = emit_test_failure_rejects(
        factory,
        agent_run_id=agent_run_id,
        nodes=nodes,
        op_ids=op_ids,
    )

    summary = summarise(agent_run_id, nodes)
    err_failures, warn_failures = _classify_severity(nodes)
    return {
        "nodes": [asdict(n) for n in summary.nodes],
        "ok": summary.ok_count,
        "fail": summary.fail_count,
        "warn": summary.warn_count,
        "skipped": summary.skipped_count,
        "rejects_inserted": rejects_inserted,
        "err_failures": err_failures,
        "warn_failures": warn_failures,
        "_nodes_internal": nodes,
    }


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
        HTTPException: 401 when the request is anonymous, 503 when
            the dbt CLI cannot be spawned.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise HTTPException(status_code=401, detail="auth required")

    models = body.get("models") if isinstance(body.get("models"), list) else None
    executor = _executor(request)
    try:
        result = await executor.compile(models=models)
    except DBTExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _result_payload(result, agent_run_id=None)


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

    Raises:
        HTTPException: 503 when the dbt CLI cannot be spawned.
    """
    require_admin(request)
    executor = _executor(request)
    try:
        result = await executor.deps()
    except DBTExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await audit(request, "dbt_deps", "dbt:deps", {"exit_code": result.exit_code})
    return _result_payload(result, agent_run_id=None)


async def _run_or_test(
    request: Request,
    *,
    body: dict[str, Any],
    op_kind: str,
) -> dict[str, Any]:
    """Shared body for ``/api/dbt/run`` and ``/api/dbt/test``.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with optional ``models`` (list[str]),
            ``full_refresh`` (bool, run-only), ``agent_run_id`` (str).
        op_kind: Either ``"run"`` or ``"test"``; selects the executor
            method and the audit-event verb.

    Returns:
        JSON envelope with executor result + bridge summary.

    Raises:
        HTTPException: 503 when dbt cannot be spawned; 500 when the
            bridge cannot emit audit rows.
    """
    require_supervisor(request)
    user = get_user(request)

    models = body.get("models") if isinstance(body.get("models"), list) else None
    agent_run_id_raw = body.get("agent_run_id")
    agent_run_id: str
    owned: bool
    if isinstance(agent_run_id_raw, str) and agent_run_id_raw:
        agent_run_id = agent_run_id_raw
        owned = False
    else:
        agent_run_id = _create_owned_run(request, user["email"])
        owned = True

    executor = _executor(request)
    try:
        if op_kind == "run":
            result = await executor.run(
                models=models,
                full_refresh=bool(body.get("full_refresh")),
            )
        else:
            result = await executor.test(models=models)
    except DBTExecutionError as exc:
        if owned:
            _finish_owned_run(request, agent_run_id, succeeded=False, exit_code=-1)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    bridge = await _emit_audit_for_run(
        request,
        agent_run_id=agent_run_id,
        result=result,
    )

    nodes_internal: list[DBTNodeResult] = bridge.pop("_nodes_internal", [])
    err_failures = int(bridge.get("err_failures", 0))
    warn_failures = int(bridge.get("warn_failures", 0))

    # Severity enforcement: only error-severity failures fail the run.
    # Warn-severity failures still let the run land as 'succeeded' but
    # fire an anomaly via the test.warned CloudEvent.
    succeeded_by_severity = result.exit_code == 0 and err_failures == 0
    if owned:
        _finish_owned_run(
            request,
            agent_run_id,
            succeeded=succeeded_by_severity,
            exit_code=result.exit_code,
        )

    await _emit_dbt_events(
        request,
        agent_run_id=agent_run_id,
        op_kind=op_kind,
        result=result,
        nodes=nodes_internal,
        err_failures=err_failures,
        warn_failures=warn_failures,
    )

    await audit(
        request,
        f"dbt_{op_kind}",
        f"dbt:{op_kind}",
        {
            "agent_run_id": agent_run_id,
            "exit_code": result.exit_code,
            "ok": bridge["ok"],
            "fail": bridge["fail"],
            "err_failures": err_failures,
            "warn_failures": warn_failures,
        },
    )

    return {**_result_payload(result, agent_run_id=agent_run_id), "summary": bridge}


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
    return await _run_or_test(request, body=body, op_kind="run")


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
    return await _run_or_test(request, body=body, op_kind="test")


# ----- read-only manifest accessors (Phase 36 Restabschluss) ---------


def _load_manifest_or_404(request: Request) -> dict[str, Any]:
    """Read ``target/manifest.json`` for the configured project.

    Centralises the 404 path: every read-only route that walks the
    manifest hits this helper so the "compile first" hint is worded
    consistently.

    Args:
        request: Incoming FastAPI request (provides settings).

    Returns:
        Parsed manifest dict.

    Raises:
        HTTPException: 404 when no manifest is on disk yet (typical
            on a fresh checkout — the agent should call
            ``POST /api/dbt/compile`` first); 500 when the file
            exists but isn't parseable JSON (corrupted target dir).
    """
    # Reuse the executor's path-resolution so manifest lookup matches
    # the path dbt actually wrote to (handles relative project_dir).
    manifest_path = _executor(request).manifest_path
    if not manifest_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "no dbt manifest on disk yet — call POST /api/dbt/compile "
                "(or POST /api/dbt/run) first to materialise "
                "target/manifest.json"
            ),
        )
    try:
        return parse_manifest(manifest_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"manifest.json is not parseable JSON: {exc}",
        ) from exc


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
        HTTPException: 401 when the request is anonymous, 404 when
            the manifest is not on disk yet, 500 when it is corrupted.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise HTTPException(status_code=401, detail="auth required")
    manifest = _load_manifest_or_404(request)
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
        HTTPException: 401 when anonymous, 404 when no manifest.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise HTTPException(status_code=401, detail="auth required")
    manifest = _load_manifest_or_404(request)
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
    agent_run_id: str = Query(description="agent_runs.id whose failures to list"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return the dbt-test failures for one agent run.

    Joins ``lineage_row_rejects`` (where ``reason='expectation_failed'``)
    with ``agent_run_operations`` so each row carries the failing
    test's ``unique_id``, the model relation it ran against, dbt's
    failure message, and the owning op id for cross-link.

    Supervisor or auditor scope required: per-run audit-axis routes
    follow the same asymmetric ladder as the rest of
    ``/api/agent-runs/{id}/audit/*`` (see :func:`require_supervisor`
    docstring).

    Args:
        request: Incoming FastAPI request.
        agent_run_id: UUID of the run whose failures to list.
        limit: Hard row cap (1-500, default 100).

    Returns:
        ``{"agent_run_id": str, "row_count": int, "rows": [...]}``.

    Raises:
        HTTPException: When the caller lacks supervisor / auditor scope
            (raised by :func:`require_supervisor`).
    """  # noqa: DOC502 — HTTPException raised inside require_supervisor
    require_supervisor(request)
    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageRowReject, AgentRunOperation)
            .join(AgentRunOperation, AgentRunOperation.id == LineageRowReject.op_id)
            .where(LineageRowReject.run_id == agent_run_id)
            .where(LineageRowReject.reason == "expectation_failed")
            .order_by(LineageRowReject.id.asc())
            .limit(limit)
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
                    "rejected_at": reject.created_at.isoformat() if reject.created_at else None,
                },
            )
    return {
        "agent_run_id": agent_run_id,
        "row_count": len(rows),
        "rows": rows,
    }
