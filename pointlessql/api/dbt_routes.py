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

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin, require_supervisor
from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models.agent_runs import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    AgentRun,
)
from pointlessql.services.dbt_bridge import (
    emit_operations_for_dbt_run,
    emit_test_failure_rejects,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
    summarise,
)
from pointlessql.services.dbt_executor import DBTExecutionError, DBTExecutor, DBTRunResult

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

    # Sprint 36.3 — every failing test becomes one row in
    # ``lineage_row_rejects`` so the cockpit's reject view + the
    # ``expectation_failure`` anomaly metric pick it up alongside
    # merge-time rejects.
    rejects_inserted = emit_test_failure_rejects(
        factory,
        agent_run_id=agent_run_id,
        nodes=nodes,
        op_ids=op_ids,
    )

    summary = summarise(agent_run_id, nodes)
    return {
        "nodes": [asdict(n) for n in summary.nodes],
        "ok": summary.ok_count,
        "fail": summary.fail_count,
        "warn": summary.warn_count,
        "skipped": summary.skipped_count,
        "rejects_inserted": rejects_inserted,
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

    if owned:
        _finish_owned_run(
            request,
            agent_run_id,
            succeeded=(result.exit_code == 0 and bridge["fail"] == 0),
            exit_code=result.exit_code,
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
