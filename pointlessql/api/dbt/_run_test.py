"""Shared body for ``/api/dbt/run`` and ``/api/dbt/test``.

The two routes differ only in (a) which executor method runs and
(b) whether the test-only auto-rollback path applies.  This module
owns the shared envelope: capture pre-versions, invoke executor,
emit audit rows + CloudEvents, build the response.  Plus the
manifest-or-404 helper used by the read-only endpoints downstream.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dbt._audit import emit_audit_for_run, emit_dbt_events
from pointlessql.api.dbt._executor import executor as build_executor
from pointlessql.api.dbt._lifecycle import (
    create_owned_run,
    finish_owned_run,
    result_payload,
)
from pointlessql.api.dbt._rollback import auto_rollback_on_error
from pointlessql.api.dependencies import get_user, require_supervisor
from pointlessql.exceptions import EngineError, ResourceNotFoundError
from pointlessql.services._executor import run_sync
from pointlessql.services.dbt import (
    DBTExecutionError,
    DBTNodeResult,
    parse_manifest,
)

logger = logging.getLogger(__name__)

# Late import path used by both _run_test and the manifest-read routes.
_capture_pre_run_versions_module = "pointlessql.api.dbt._audit"


async def run_or_test(
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
        DBTExecutionError: 503 when dbt cannot be spawned (rendered
            by the centralised handler).
    """
    from pointlessql.api.dbt._audit import capture_pre_run_versions

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
        agent_run_id = create_owned_run(request, user["email"])
        owned = True

    executor = build_executor(request)

    # Capture pre-run Delta versions for every model in the existing
    # manifest *before* dbt mutates anything.  Combined with the
    # post-run capture inside emit_audit_for_run, this populates
    # ``delta_version_before`` / ``delta_version_after`` on each
    # emitted ``dbt_model`` op — the anchors ``pql.rollback`` needs
    # to undo a dbt-driven write.  Best-effort: a fresh project
    # without a manifest yields an empty map.
    pre_versions = await run_sync(
        capture_pre_run_versions,
        request,
        executor.manifest_path,
    )

    try:
        if op_kind == "run":
            result = await executor.run(
                models=models,
                full_refresh=bool(body.get("full_refresh")),
            )
        else:
            result = await executor.test(models=models)
    except DBTExecutionError:
        if owned:
            finish_owned_run(request, agent_run_id, succeeded=False, exit_code=-1)
        # DBTExecutionError is a PointlessSQLError(503); the
        # centralised handler renders it directly.
        raise

    bridge = await emit_audit_for_run(
        request,
        agent_run_id=agent_run_id,
        result=result,
        pre_versions=pre_versions,
    )

    nodes_internal: list[DBTNodeResult] = bridge.pop("_nodes_internal", [])
    err_failures = int(bridge.get("err_failures", 0))
    warn_failures = int(bridge.get("warn_failures", 0))

    # Severity enforcement: only error-severity failures fail the run.
    # Warn-severity failures still let the run land as 'succeeded' but
    # fire an anomaly via the test.warned CloudEvent.
    succeeded_by_severity = result.exit_code == 0 and err_failures == 0
    if owned:
        finish_owned_run(
            request,
            agent_run_id,
            succeeded=succeeded_by_severity,
            exit_code=result.exit_code,
        )

    await emit_dbt_events(
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

    response: dict[str, Any] = {
        **result_payload(result, agent_run_id=agent_run_id),
        "summary": bridge,
    }

    # Auto-rollback only fires on the test path: model writes are
    # reverted *because tests failed*, never as a side-effect of the
    # run itself.  When the run path is taken we skip even the flag
    # parsing so the body shape stays narrow.
    if op_kind == "test":
        auto_rollback = bool(body.get("auto_rollback", False))
        rollback_payload = await auto_rollback_on_error(
            request,
            agent_run_id=agent_run_id,
            err_failures=err_failures,
            auto_rollback=auto_rollback,
        )
        if rollback_payload is not None:
            response["auto_rollback"] = rollback_payload

    return response


def load_manifest_or_404(request: Request) -> dict[str, Any]:
    """Read ``target/manifest.json`` for the configured project.

    Centralises the 404 path: every read-only route that walks the
    manifest hits this helper so the "compile first" hint is worded
    consistently.

    Args:
        request: Incoming FastAPI request (provides settings).

    Returns:
        Parsed manifest dict.

    Raises:
        ResourceNotFoundError: 404 when no manifest is on disk yet
            (typical on a fresh checkout — the agent should call
            ``POST /api/dbt/compile`` first).
        EngineError: 500 when the file exists but isn't parseable
            JSON (corrupted target dir).
    """
    # Reuse the executor's path-resolution so manifest lookup matches
    # the path dbt actually wrote to (handles relative project_dir).
    manifest_path = build_executor(request).manifest_path
    if not manifest_path.is_file():
        raise ResourceNotFoundError(
            "no dbt manifest on disk yet — call POST /api/dbt/compile "
            "(or POST /api/dbt/run) first to materialise "
            "target/manifest.json"
        )
    try:
        return parse_manifest(manifest_path)
    except ValueError as exc:
        raise EngineError(f"manifest.json is not parseable JSON: {exc}") from exc
