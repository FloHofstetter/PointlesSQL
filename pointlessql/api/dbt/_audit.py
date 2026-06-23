"""Audit-trail emission for dbt CLI invocations.

Five helpers that turn the executor's manifest/run-results artefacts
into ``agent_run_operations`` rows, fire the per-run CloudEvents,
and capture pre/post Delta versions for rollback anchoring.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request

from pointlessql.exceptions import AuditUnavailableError
from pointlessql.services.dbt import (
    DBTNodeResult,
    DBTRunResult,
    as_dict,
    capture_delta_versions,
    emit_operations_for_dbt_run,
    emit_test_failure_rejects,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
    summarise,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DBT_RUN_COMPLETED,
    EVENT_TYPE_DBT_TEST_FAILED,
    EVENT_TYPE_DBT_TEST_WARNED,
    emit_governance_event,
)

logger = logging.getLogger(__name__)


def classify_severity(nodes: list[DBTNodeResult]) -> tuple[int, int]:
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


async def emit_dbt_events(
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


def model_relations_from_manifest_path(manifest_path: Path) -> list[str]:
    """Read ``manifest_path`` and return every model node's ``relation_name``.

    Best-effort: missing or unparseable manifest yields an empty list.
    Used by :func:`capture_pre_run_versions` to identify which
    targets to read Delta versions for *before* dbt mutates them.

    Args:
        manifest_path: Path to ``target/manifest.json``.

    Returns:
        Deduplicated list of qualified relation names; empty when
        no manifest exists yet (typical on a fresh project).
    """
    if not manifest_path.is_file():
        return []
    try:
        manifest = parse_manifest(manifest_path)
    except FileNotFoundError, ValueError:
        return []
    nodes = as_dict(manifest.get("nodes"))
    out: list[str] = []
    for raw_node in nodes.values():
        node = as_dict(raw_node)
        if node.get("resource_type") != "model":
            continue
        rel = node.get("relation_name")
        if isinstance(rel, str) and rel:
            out.append(rel)
    return list(dict.fromkeys(out))


def capture_pre_run_versions(
    request: Request,
    manifest_path: Path,
) -> dict[str, int | None]:
    """Capture Delta versions for every model relation *before* dbt runs.

    The pre-version map drives ``delta_version_before`` on the
    emitted ``dbt_model`` ops, which is what ``pql.rollback`` needs
    to restore the prior state.  Without this, every dbt-targeted
    rollback fails with ``RollbackInvalid`` because the bridge would
    have written ``None``.

    Best-effort: a missing manifest, a missing app-state UC client,
    or any per-relation failure all map to an empty / partial dict.

    Args:
        request: Incoming FastAPI request (carries ``app.state.uc_client``).
        manifest_path: Path to ``target/manifest.json`` from the
            *previous* compile / run.  ``None`` (file-missing) is
            handled gracefully.

    Returns:
        ``{relation: version|None}`` covering every model relation
        in the manifest.
    """
    relations = model_relations_from_manifest_path(manifest_path)
    if not relations:
        return {}
    uc_client = getattr(request.app.state, "uc_client", None)
    if uc_client is None:
        return {}
    return capture_delta_versions(uc_client._client, relations)  # noqa: SLF001


async def emit_audit_for_run(
    request: Request,
    *,
    agent_run_id: str,
    result: DBTRunResult,
    pre_versions: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """Parse manifest + run_results and emit ``agent_run_operations`` rows.

    Args:
        request: Incoming request (for the session factory).
        agent_run_id: Owning run id.
        result: Executor outcome with manifest + run_results paths.
        pre_versions: Map of ``{relation: delta_version_before}`` captured
            before dbt ran (via :func:`capture_pre_run_versions`).
            ``None`` (default) keeps ``delta_version_before`` as ``None``
            on every emitted op — the legacy shape.

    Returns:
        Summary dict with counts and per-node payload (used by the
        callers to build their HTTP response).

    Raises:
        AuditUnavailableError: 503 when the bridge cannot emit
            operation rows.
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

    # Capture post-run versions for every model relation that landed
    # this run.  Combined with pre_versions (passed in by the caller),
    # this populates ``delta_version_before`` / ``delta_version_after``
    # on each emitted op so ``pql.rollback`` has the version anchors
    # it needs.  Best-effort: targets missing from soyuz or written
    # to non-Delta storage map to None and rollback then refuses with
    # ``RollbackInvalid`` for those (the correct conservative path).
    post_relations = sorted({n.relation_name for n in nodes if n.relation_name})
    uc_client = getattr(request.app.state, "uc_client", None)
    post_versions: dict[str, int | None] = (
        capture_delta_versions(uc_client._client, post_relations)  # noqa: SLF001
        if uc_client is not None and post_relations
        else {}
    )

    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    try:
        op_ids = emit_operations_for_dbt_run(
            factory,
            agent_run_id=agent_run_id,
            nodes=nodes,
            started_at=started_at,
            pre_versions=pre_versions,
            post_versions=post_versions,
        )
    except AuditUnavailableError:
        logger.exception("dbt bridge failed to emit operations")
        raise

    rejects_inserted = emit_test_failure_rejects(
        factory,
        agent_run_id=agent_run_id,
        nodes=nodes,
        op_ids=op_ids,
    )

    summary = summarise(agent_run_id, nodes)
    err_failures, warn_failures = classify_severity(nodes)
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
