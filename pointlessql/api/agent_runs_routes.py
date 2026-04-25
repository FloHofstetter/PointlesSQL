"""Agent-run registry endpoints — Sprint 13.2.

External runtimes (Hermes, OpenShell, a curl'd cron job) POST here to
register a run they are about to execute and again when it
terminates.  PointlesSQL stores the row, links to any ``notebook_outputs``
/ ``notebook_cell_runs`` rows the runtime later writes, and exposes
the result via :mod:`pointlessql.api.runs_routes` for humans.

No executor in this sprint — the runtime owns process lifecycle; we
only own the supervision record.  The ``X-Principal`` header is read
on ``POST /api/agent-runs`` so the registration is attributed to the
agent's human principal from day one (Sprint 13.6 extends it through
the PQL session).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Body, Header, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AgentRunSource, AgentRunToolCall
from pointlessql.models.agent_runs import (
    STATUS_QUEUED,
    TERMINAL_STATUSES,
    VALID_STATUSES,
    AgentRun,
)
from pointlessql.services.agent_runs import (
    EVENT_TYPE_STARTED,
    EVENT_TYPE_TOOL_CALL,
    emit_agent_run_event,
    event_type_for_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-runs"])


def serialize_agent_run(row: AgentRun) -> dict[str, Any]:
    """Render an :class:`AgentRun` ORM row into a JSON-safe dict.

    The shape matches what ``/runs`` and ``/runs/{id}`` expect in
    their template context, so the same serializer powers the HTML
    and JSON responses without a second mapping.

    Args:
        row: The ORM row to serialize.

    Returns:
        Plain dict with ISO-formatted timestamps and a decoded
        ``tables_touched`` list.
    """
    tables: list[str] = []
    if row.tables_touched:
        try:
            parsed: Any = json.loads(row.tables_touched)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            tables = [
                str(item)  # pyright: ignore[reportUnknownArgumentType]
                for item in parsed  # pyright: ignore[reportUnknownVariableType]
            ]
    runtime_versions: dict[str, Any] = {}
    if row.runtime_versions:
        try:
            decoded: Any = json.loads(row.runtime_versions)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            runtime_versions = decoded  # pyright: ignore[reportUnknownVariableType]
    return {
        "id": row.id,
        "principal": row.principal,
        "agent_id": row.agent_id,
        "notebook_path": row.notebook_path,
        "source_snapshot_sha": row.source_snapshot_sha,
        "status": row.status,
        "cost_est": float(row.cost_est) if row.cost_est is not None else None,
        "tables_touched": tables,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "exit_code": row.exit_code,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "denied_reason": row.denied_reason,
        "runtime_versions": runtime_versions,
    }


def _coerce_tables_touched(value: Any) -> str | None:
    """Normalize the ``tables_touched`` payload into a JSON-encoded list.

    Accepts a ``list[str]`` from JSON bodies; rejects anything else
    so a malformed payload cannot round-trip through the store.

    Args:
        value: Raw field value from the request body.

    Returns:
        JSON-encoded array text, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is neither ``None`` nor a list
            of strings.
    """
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value  # pyright: ignore[reportUnknownVariableType]
    ):
        raise ValidationError("tables_touched must be a list of strings")
    return json.dumps(value)


def _coerce_cost_est(value: Any) -> Decimal | None:
    """Parse ``cost_est`` into a :class:`Decimal`, rejecting bad shapes.

    Args:
        value: Raw field value from the request body.

    Returns:
        The parsed :class:`Decimal`, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is not null, numeric, or a
            numeric string.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError("cost_est must be numeric") from exc


@router.post("/api/agent-runs")
async def api_create_agent_run(
    request: Request,
    body: dict[str, Any] = Body(...),
    x_principal: str | None = Header(default=None, alias="X-Principal"),
) -> dict[str, Any]:
    """Register a new agent run from an external runtime.

    Sprint 13.8 hardened the contract: ``source`` and
    ``runtime_versions`` are required.  The server hashes the source
    bytes server-side and persists them in ``agent_run_sources``
    inside the same transaction as the new ``agent_runs`` row, so a
    post-run edit of the on-disk ``.py`` cannot silently rewrite
    history.  When the runtime supplies a
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
            "runtime_versions must be a non-empty mapping of "
            "{component: version_string}"
        )
    runtime_versions: dict[str, str] = {}
    for key, value in runtime_versions_raw.items():  # type: ignore[union-attr]
        if not isinstance(key, str) or not key:
            raise ValidationError("runtime_versions keys must be non-empty strings")
        if not isinstance(value, str):
            raise ValidationError(
                f"runtime_versions[{key!r}] must be a string version"
            )
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

    tables_touched = _coerce_tables_touched(body.get("tables_touched"))
    cost_est = _coerce_cost_est(body.get("cost_est"))

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

    factory = request.app.state.session_factory
    with factory() as session:
        existing = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if existing is not None:
            raise ValidationError(f"agent run {run_id!r} already registered")
        row = AgentRun(
            id=run_id,
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
    await emit_agent_run_event(
        EVENT_TYPE_STARTED, payload, session_factory=factory
    )
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
            ``finished_at`` / ``denied_reason``.

    Returns:
        The serialized, now-terminal :class:`AgentRun` row.

    Raises:
        CatalogNotFoundError: No run with that id exists.
        ValidationError: Status is missing, not terminal, or the run
            is already in a terminal state.
    """
    status_raw = body.get("status")
    if status_raw not in TERMINAL_STATUSES:
        raise ValidationError(
            f"status must be one of {sorted(TERMINAL_STATUSES)} to finish a run"
        )

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

    cost_est = _coerce_cost_est(body["cost_est"]) if "cost_est" in body else None
    tables_touched = (
        _coerce_tables_touched(body["tables_touched"]) if "tables_touched" in body else None
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
        if cost_est is not None:
            row.cost_est = cost_est
        if tables_touched is not None:
            row.tables_touched = tables_touched
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "finish_agent_run",
        f"agent_run:{run_id}",
        {"status": status_raw, "exit_code": exit_code},
    )
    payload = serialize_agent_run(row)
    terminal_event = event_type_for_status(status_raw)
    if terminal_event is not None:
        await emit_agent_run_event(
            terminal_event, payload, session_factory=factory
        )
    return payload


@router.get("/api/agent-runs")
async def api_list_agent_runs(request: Request, limit: int = 100) -> dict[str, Any]:
    """List recent agent runs as JSON.

    A thin companion to ``GET /runs`` for machine consumers (the
    Sprint 13.7 Hermes plugin, curl probes, dashboards).  Ordered
    newest-first by ``started_at``.  No filtering yet — the richer
    filter bar lands with Sprint 13.4.

    Args:
        request: Incoming FastAPI request.
        limit: Maximum number of rows to return.  Clamped to 500.

    Returns:
        ``{"runs": [...]}`` with each entry shaped by
        :func:`serialize_agent_run`.
    """
    effective_limit = max(1, min(int(limit), 500))
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(effective_limit)
        rows = list(session.scalars(stmt).all())
        payload = [serialize_agent_run(r) for r in rows]
    return {"runs": payload}


@router.post("/api/agent-runs/{run_id}/approve")
async def api_approve_agent_run(
    request: Request, run_id: str,
) -> dict[str, Any]:
    """Admin-only approval for a run pending ``needs_approval``.

    Sprint 13.2 lands the endpoint so Sprint 13.4 can surface the
    button without a second backend change.  Transitions the row to
    ``approved`` and records the approving admin + timestamp.

    Args:
        request: Incoming FastAPI request.
        run_id: The UUID string of the run to approve.

    Returns:
        The serialized row after the transition.

    Raises:
        CatalogNotFoundError: No run with that id.
        ValidationError: Run is not in ``needs_approval``.
    """
    require_admin(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status != "needs_approval":
            raise ValidationError(
                f"agent run {run_id!r} is {row.status!r}, cannot approve"
            )
        row.status = "approved"
        row.approved_by = user["email"]
        row.approved_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "approve_agent_run", f"agent_run:{run_id}")
    return serialize_agent_run(row)


@router.post("/api/agent-runs/{run_id}/deny")
async def api_deny_agent_run(
    request: Request, run_id: str, body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Admin-only denial for a run pending ``needs_approval``.

    Terminal transition: the row moves straight to ``denied`` with
    ``finished_at`` set.  A ``reason`` body field is optional but
    recommended for audit readability.

    Args:
        request: Incoming FastAPI request.
        run_id: The UUID string of the run to deny.
        body: Optional JSON with ``reason`` text.

    Returns:
        The serialized, terminal row.

    Raises:
        CatalogNotFoundError: No run with that id.
        ValidationError: Run is not in ``needs_approval``.
    """
    require_admin(request)
    reason_raw = body.get("reason")
    reason = (
        str(reason_raw).strip()
        if isinstance(reason_raw, str) and reason_raw.strip()
        else None
    )
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status != "needs_approval":
            raise ValidationError(
                f"agent run {run_id!r} is {row.status!r}, cannot deny"
            )
        row.status = "denied"
        row.denied_reason = reason
        row.finished_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "deny_agent_run",
        f"agent_run:{run_id}",
        {"reason": reason},
    )
    return serialize_agent_run(row)


@router.post("/api/agent-runs/{run_id}/tool-call")
async def api_record_tool_call(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Record one LLM tool invocation against an agent run (Sprint 13.7.4).

    The Hermes plugin's ``post_tool_call`` hook posts here for any
    tool whose name starts with ``pql_``.  Persists the row in
    ``agent_run_tool_calls`` and emits a Sprint-13.3-style
    ``pointlessql.agent_run.tool_call`` CloudEvent so external
    subscribers can rebuild the agent's reasoning trace from the
    event stream.

    The endpoint is intentionally lenient on missing optional
    fields — the plugin should never have to know the schema; if
    ``args_json`` is empty we store ``"{}"``, if ``called_at`` is
    missing we use the request wall-clock.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the owning agent run.
        body: JSON ``{tool_name, args_json?, result_summary?,
            duration_ms?, called_at?}``.

    Returns:
        ``{"id": <new_row_id>, "tool_name": ..., "called_at": ...}``.

    Raises:
        ValidationError: Missing/empty ``tool_name``.
        CatalogNotFoundError: No run with that id.
    """
    tool_name_raw = body.get("tool_name")
    if not isinstance(tool_name_raw, str) or not tool_name_raw.strip():
        raise ValidationError("tool_name must be a non-empty string")
    tool_name = tool_name_raw.strip()[:64]

    args_json_raw = body.get("args_json")
    if isinstance(args_json_raw, str) and args_json_raw.strip():
        args_json = args_json_raw
    elif isinstance(args_json_raw, dict):
        args_json = json.dumps(args_json_raw, sort_keys=True, default=str)
    else:
        args_json = "{}"

    summary_raw = body.get("result_summary")
    result_summary: str | None = None
    if isinstance(summary_raw, str) and summary_raw:
        result_summary = summary_raw[:2000]

    duration_raw = body.get("duration_ms")
    duration_ms: int | None = None
    if isinstance(duration_raw, (int, float)) and duration_raw >= 0:
        duration_ms = int(duration_raw)

    called_at_raw = body.get("called_at")
    if isinstance(called_at_raw, str) and called_at_raw.strip():
        try:
            called_at = datetime.fromisoformat(called_at_raw)
        except ValueError as exc:
            raise ValidationError(
                "called_at must be ISO-8601 when provided"
            ) from exc
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=UTC)
    else:
        called_at = datetime.now(UTC)

    factory = request.app.state.session_factory
    with factory() as session:
        run_row = session.scalar(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        if run_row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        tool_row = AgentRunToolCall(
            agent_run_id=run_id,
            tool_name=tool_name,
            args_json=args_json,
            result_summary=result_summary,
            duration_ms=duration_ms,
            called_at=called_at,
        )
        session.add(tool_row)
        session.commit()
        session.refresh(tool_row)
        new_id = tool_row.id
        session.expunge(tool_row)

    # ``id`` keys the CloudEvent's source URL to the parent run id
    # so emit_agent_run_event() persists the envelope under the
    # correct ``agent_run_events.agent_run_id`` FK.  The
    # tool-call row's primary key surfaces as ``tool_call_id``.
    payload = {
        "id": run_id,
        "tool_call_id": new_id,
        "tool_name": tool_name,
        "called_at": called_at.isoformat(),
        "duration_ms": duration_ms,
    }
    await audit(
        request,
        "record_agent_run_tool_call",
        f"agent_run:{run_id}",
        {"tool_name": tool_name},
    )
    await emit_agent_run_event(
        EVENT_TYPE_TOOL_CALL, payload, session_factory=factory
    )
    return payload


__all__ = ["router", "serialize_agent_run"]
