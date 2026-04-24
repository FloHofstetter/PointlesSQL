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
from pointlessql.models.agent_runs import (
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

    The caller supplies the run id (UUIDv4 string) so lifecycle POSTs
    from the same runtime can address the row without a lookup
    round-trip.  When the id is omitted we mint one; either way the
    response echoes it.  The ``notebook_path`` is required because
    the run-detail view needs it to render the cell card deck even
    if no per-cell data has been written yet.

    Args:
        request: Incoming FastAPI request.
        body: JSON payload with optional ``id``, ``agent_id``,
            required ``notebook_path``, optional
            ``source_snapshot_sha`` / ``status`` / ``cost_est`` /
            ``tables_touched`` / ``started_at``.
        x_principal: ``X-Principal`` header value.  Overrides any
            ``principal`` body field so the HTTP hop is authoritative.

    Returns:
        The serialized :class:`AgentRun` row.

    Raises:
        ValidationError: When ``notebook_path`` is missing, ``status``
            is unknown, or any typed field is malformed.
    """
    notebook_path_raw = body.get("notebook_path")
    if not isinstance(notebook_path_raw, str) or not notebook_path_raw.strip():
        raise ValidationError("notebook_path must be a non-empty string")
    notebook_path = notebook_path_raw.strip()

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
    source_snapshot_sha = (
        str(snapshot_raw).strip()
        if isinstance(snapshot_raw, str) and snapshot_raw.strip()
        else None
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
            source_snapshot_sha=source_snapshot_sha,
            status=status_raw,
            cost_est=cost_est,
            tables_touched=tables_touched,
            started_at=started_at,
        )
        session.add(row)
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
    await emit_agent_run_event(EVENT_TYPE_STARTED, payload)
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
        await emit_agent_run_event(terminal_event, payload)
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


__all__ = ["router", "serialize_agent_run"]
