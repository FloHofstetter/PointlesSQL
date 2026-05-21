"""Agent-run registration + termination endpoints.

The runtime POSTs to ``/api/agent-runs`` to register a run before
it executes, then POSTs to ``/api/agent-runs/{id}/finish`` when the
process exits.  Source bytes hash server-side and persist in
``agent_run_sources`` inside the same transaction as the new
``agent_runs`` row, so a post-run edit of the on-disk ``.py``
cannot silently rewrite history.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Header, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.agent_runs_routes._anomaly_persist import persist_run_anomaly
from pointlessql.api.agent_runs_routes._serializers import (
    coerce_cost_est,
    coerce_cost_gate_trigger,
    coerce_tables_touched,
    serialize_agent_run,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AgentRunSource
from pointlessql.models.agent._runs import (
    STATUS_QUEUED,
    TERMINAL_STATUSES,
    VALID_STATUSES,
    AgentRun,
)
from pointlessql.services.agent_runs import (
    EVENT_TYPE_STARTED,
    emit_agent_run_event,
    event_type_for_status,
)
from pointlessql.services.notifications.fanout import fanout_event

router = APIRouter()


@router.post("/api/agent-runs")
async def api_create_agent_run(
    request: Request,
    body: dict[str, Any] = Body(...),
    x_principal: str | None = Header(default=None, alias="X-Principal"),
) -> dict[str, Any]:
    """Register a new agent run from an external runtime.

    Contract: ``source`` and ``runtime_versions`` are required.  The
    server hashes the source bytes server-side and persists them in
    ``agent_run_sources`` inside the same transaction as the new
    ``agent_runs`` row, so a post-run edit of the on-disk ``.py``
    cannot silently rewrite history.  When the runtime supplies a
    ``source_snapshot_sha`` and it disagrees with the computed
    digest, registration fails with 422 (tamper-detection).

    Args:
        request: Incoming FastAPI request.
        body: JSON payload.  Required: ``notebook_path``,
            ``source`` (UTF-8 ``.py`` text), ``runtime_versions``
            (``{name: version}`` mapping with at least one entry).
            Optional: ``id``, ``agent_id``, ``principal``,
            ``source_snapshot_sha`` (validated against the computed
            digest), ``status``, ``cost_est``, ``tables_touched``,
            ``started_at``.
        x_principal: ``X-Principal`` header value.  Overrides any
            ``principal`` body field so the HTTP hop is authoritative.

    Returns:
        The serialized :class:`AgentRun` row.

    Raises:
        ValidationError: When any required field is missing,
            ``status`` is unknown, ``source_snapshot_sha`` mismatches
            the computed digest, or any typed field is malformed.
    """
    notebook_path_raw = body.get("notebook_path")
    if not isinstance(notebook_path_raw, str) or not notebook_path_raw.strip():
        raise ValidationError("notebook_path must be a non-empty string")
    notebook_path = notebook_path_raw.strip()

    source_raw = body.get("source")
    if not isinstance(source_raw, str) or not source_raw:
        raise ValidationError("source must be a non-empty string")
    source_bytes = source_raw
    computed_sha = hashlib.sha256(source_bytes.encode("utf-8")).hexdigest()

    runtime_versions_raw = body.get("runtime_versions")
    if not isinstance(runtime_versions_raw, dict) or not runtime_versions_raw:
        raise ValidationError(
            "runtime_versions must be a non-empty mapping of {component: version_string}"
        )
    runtime_versions: dict[str, str] = {}
    for key, value in runtime_versions_raw.items():  # type: ignore[union-attr]
        if not isinstance(key, str) or not key:
            raise ValidationError("runtime_versions keys must be non-empty strings")
        if not isinstance(value, str):
            raise ValidationError(f"runtime_versions[{key!r}] must be a string version")
        runtime_versions[key] = value

    run_id_raw = body.get("id")
    if run_id_raw in (None, ""):
        run_id = str(uuid.uuid4())
    else:
        run_id = str(run_id_raw).strip()
        if not run_id:
            raise ValidationError("id must be a non-empty string when provided")

    status_raw = body.get("status", STATUS_QUEUED)
    if not isinstance(status_raw, str) or status_raw not in VALID_STATUSES:
        raise ValidationError(f"status must be one of {sorted(VALID_STATUSES)}")

    agent_id_raw = body.get("agent_id")
    agent_id = (
        str(agent_id_raw).strip()
        if isinstance(agent_id_raw, str) and agent_id_raw.strip()
        else None
    )

    snapshot_raw = body.get("source_snapshot_sha")
    declared_sha: str | None = None
    if isinstance(snapshot_raw, str) and snapshot_raw.strip():
        declared_sha = snapshot_raw.strip().lower()
        if declared_sha != computed_sha:
            raise ValidationError(
                f"source_snapshot_sha mismatch: declared {declared_sha!r} "
                f"but computed {computed_sha!r} from the supplied source"
            )

    principal: str | None
    if x_principal and x_principal.strip():
        principal = x_principal.strip()
    else:
        body_principal = body.get("principal")
        principal = (
            str(body_principal).strip()
            if isinstance(body_principal, str) and body_principal.strip()
            else None
        )

    tables_touched = coerce_tables_touched(body.get("tables_touched"))
    cost_est = coerce_cost_est(body.get("cost_est"))

    started_at_raw = body.get("started_at")
    if isinstance(started_at_raw, str) and started_at_raw.strip():
        try:
            started_at = datetime.fromisoformat(started_at_raw)
        except ValueError as exc:
            raise ValidationError("started_at must be an ISO-8601 timestamp") from exc
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
    else:
        started_at = datetime.now(UTC)

    # Every new agent_run lands in the workspace the request
    # resolved to.  The middleware already attached
    # request.state.workspace_id (with the X-Workspace > api_key pin
    # > cookie > user.default > 1 priority chain).  The FK column
    # cascades to agent_run_sources via explicit assignment.
    workspace_id_for_run = int(getattr(request.state, "workspace_id", 1))

    factory = request.app.state.session_factory
    with factory() as session:
        existing = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if existing is not None:
            raise ValidationError(f"agent run {run_id!r} already registered")
        row = AgentRun(
            id=run_id,
            workspace_id=workspace_id_for_run,
            principal=principal,
            agent_id=agent_id,
            notebook_path=notebook_path,
            source_snapshot_sha=computed_sha,
            status=status_raw,
            cost_est=cost_est,
            tables_touched=tables_touched,
            started_at=started_at,
            runtime_versions=json.dumps(runtime_versions, sort_keys=True),
        )
        session.add(row)
        # Flush before adding the FK-dependent child row so SQLite's
        # immediate FK enforcement (PRAGMA foreign_keys=ON, set in
        # pointlessql.db) sees the parent in the same transaction.
        session.flush()
        source_row = AgentRunSource(
            workspace_id=workspace_id_for_run,
            agent_run_id=run_id,
            source_bytes=source_bytes,
            source_sha=computed_sha,
            captured_at=started_at,
        )
        session.add(source_row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "create_agent_run",
        f"agent_run:{run_id}",
        {"notebook_path": notebook_path, "agent_id": agent_id, "status": status_raw},
    )
    payload = serialize_agent_run(row)
    await emit_agent_run_event(EVENT_TYPE_STARTED, payload, session_factory=factory)
    return payload


@router.post("/api/agent-runs/{run_id}/finish")
async def api_finish_agent_run(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Transition an active run into a terminal state.

    The runtime POSTs here when its process exits.  The ``status``
    field is required and must be a terminal value (``succeeded``,
    ``failed``, ``denied``).  Already-terminal runs reject further
    updates — once a run has finished, its row is immutable
    supervision history.

    Args:
        request: Incoming FastAPI request.
        run_id: The UUID string used on creation.
        body: JSON payload with required ``status`` and optional
            ``exit_code`` / ``cost_est`` / ``tables_touched`` /
            ``finished_at`` / ``denied_reason`` /
            ``cost_gate_trigger`` (JSON object captured from
            ``/api/sql/explain`` when the gate denied the query).

    Returns:
        The serialized, now-terminal :class:`AgentRun` row.

    Raises:
        CatalogNotFoundError: No run with that id exists.
        ValidationError: Status is missing, not terminal, or the run
            is already in a terminal state.
    """
    status_raw = body.get("status")
    if status_raw not in TERMINAL_STATUSES:
        raise ValidationError(f"status must be one of {sorted(TERMINAL_STATUSES)} to finish a run")

    exit_code_raw = body.get("exit_code")
    exit_code: int | None = None
    if exit_code_raw is not None:
        try:
            exit_code = int(exit_code_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError("exit_code must be an integer when provided") from exc

    denied_reason_raw = body.get("denied_reason")
    denied_reason = (
        str(denied_reason_raw).strip()
        if isinstance(denied_reason_raw, str) and denied_reason_raw.strip()
        else None
    )

    cost_gate_trigger = (
        coerce_cost_gate_trigger(body["cost_gate_trigger"]) if "cost_gate_trigger" in body else None
    )

    cost_est = coerce_cost_est(body["cost_est"]) if "cost_est" in body else None
    tables_touched = (
        coerce_tables_touched(body["tables_touched"]) if "tables_touched" in body else None
    )

    finished_at_raw = body.get("finished_at")
    if isinstance(finished_at_raw, str) and finished_at_raw.strip():
        try:
            finished_at = datetime.fromisoformat(finished_at_raw)
        except ValueError as exc:
            raise ValidationError("finished_at must be an ISO-8601 timestamp") from exc
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=UTC)
    else:
        finished_at = datetime.now(UTC)

    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status in TERMINAL_STATUSES:
            raise ValidationError(
                f"agent run {run_id!r} already finished with status {row.status!r}"
            )
        row.status = status_raw
        row.finished_at = finished_at
        if exit_code is not None:
            row.exit_code = exit_code
        if denied_reason is not None:
            row.denied_reason = denied_reason
        if cost_gate_trigger is not None:
            row.cost_gate_trigger = cost_gate_trigger
        if cost_est is not None:
            row.cost_est = cost_est
        if tables_touched is not None:
            row.tables_touched = tables_touched
        session.commit()
        session.refresh(row)
        session.expunge(row)
    persist_run_anomaly(request, run_id)
    await audit(
        request,
        "finish_agent_run",
        f"agent_run:{run_id}",
        {"status": status_raw, "exit_code": exit_code},
    )
    payload = serialize_agent_run(row)
    terminal_event = event_type_for_status(status_raw)
    if terminal_event is not None:
        await emit_agent_run_event(terminal_event, payload, session_factory=factory)
        # Phase 81.K.6 — surface agent-run lifecycle in the feed.
        # The fanout dispatcher's existing follower-resolution walks
        # the polymorphic ``SocialFollow`` set; an empty follower
        # list is a no-op so this wiring is safe regardless of
        # whether anyone currently follows runs.
        verb = "completed" if terminal_event.endswith(".completed") else "failed"
        summary = (
            f"Agent run #{run_id} {verb}"
            + (f" (exit {exit_code})" if exit_code is not None else "")
        )
        try:
            fanout_event(
                factory,
                event_type=terminal_event,
                entity_kind="run",
                entity_ref=str(run_id),
                workspace_id=int(row.workspace_id),
                actor_user_id=None,
                source_url=f"/runs/{run_id}",
                summary_md=summary,
            )
        except Exception:  # noqa: BLE001 — fanout must never break the run
            # bare-broad-ok: terminal-event fanout is best-effort
            logger.exception("agent_run_fanout_failed run_id=%s", run_id)
    return payload
