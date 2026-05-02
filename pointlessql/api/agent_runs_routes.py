"""Agent-run registry endpoints.

External runtimes (Hermes, OpenShell, a curl'd cron job) POST here to
register a run they are about to execute and again when it
terminates.  PointlesSQL stores the row, links to any ``notebook_outputs``
/ ``notebook_cell_runs`` rows the runtime later writes, and exposes
the result via :mod:`pointlessql.api.runs_routes` for humans.

No executor lives here — the runtime owns process lifecycle; we
only own the supervision record.  The ``X-Principal`` header is read
on ``POST /api/agent-runs`` so the registration is attributed to the
agent's human principal, and the same header is propagated through
the PQL session so downstream UC checks resolve against the same
identity.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Body, Header, Query, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    get_user,
    require_admin,
    require_supervisor,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import (
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
    LineageColumnMap,
    LineageValueChange,
    QueryHistory,
)
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
from pointlessql.services.query_history import record_query
from pointlessql.services.run_diff import (
    AlignmentMode,
    build_detail_diff,
    build_lineage_diff,
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
    cost_gate_trigger: dict[str, Any] | None = None
    if row.cost_gate_trigger:
        try:
            decoded_trigger: Any = json.loads(row.cost_gate_trigger)
        except json.JSONDecodeError:
            decoded_trigger = None
        if isinstance(decoded_trigger, dict):
            cost_gate_trigger = decoded_trigger  # pyright: ignore[reportUnknownVariableType]
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
        "cost_gate_trigger": cost_gate_trigger,
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
        isinstance(item, str)
        for item in value  # pyright: ignore[reportUnknownVariableType]
    ):
        raise ValidationError("tables_touched must be a list of strings")
    return json.dumps(value)


def _coerce_cost_gate_trigger(value: Any) -> str | None:
    """Validate and JSON-encode the ``cost_gate_trigger`` snapshot.

    The runtime forwards the dict the cost gate emitted on
    ``/api/sql/explain`` (see ``sql_routes.api_sql_explain``) so the
    reviewer can see the EXPLAIN plan, threshold, and estimated cost
    that produced the verdict without re-running the query.

    Args:
        value: Raw field value from the request body.

    Returns:
        JSON-encoded mapping text, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is neither ``None`` nor a
            JSON-serializable mapping.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError("cost_gate_trigger must be a JSON object")
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("cost_gate_trigger must be JSON-serializable") from exc


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
        _coerce_cost_gate_trigger(body["cost_gate_trigger"])
        if "cost_gate_trigger" in body
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
        if cost_gate_trigger is not None:
            row.cost_gate_trigger = cost_gate_trigger
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
        await emit_agent_run_event(terminal_event, payload, session_factory=factory)
    return payload


@router.get("/api/agent-runs/operations")
async def api_list_agent_run_operations(
    request: Request,
    target: str | None = Query(default=None, description="catalog.schema.table"),
    errored: bool = Query(default=False, description="Only return rows with error_message"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Filterable list of ``agent_run_operations`` rows.

    Backs the ``pql_recent_failures`` Hermes tool — when an agent is
    about to retry a write, asking "did this exact target fail
    recently for someone else?" should be one HTTP call instead of a
    join through ``/runs``.

    All three filters are optional and AND-ed together.  Rows are
    returned newest-first by ``started_at`` so the freshest failure
    is at the top.

    Args:
        request: Incoming FastAPI request.
        target: Three-part UC identifier to scope to.  ``None``
            returns rows across every target.
        errored: When ``True`` (or any truthy query value), only
            rows with a non-null ``error_message`` are returned.
        since: ISO-8601 timestamp (UTC); rows with
            ``started_at >= since`` are kept.  ``None`` keeps all.
        limit: Hard cap (default 50, max 500).

    Returns:
        ``{"operations": [...]}`` with each entry shaped like the
        per-run operations payload from ``runs_routes._load_operations_for_run``
        plus an ``agent_run_id`` so the caller can drill back into
        ``/runs/{id}``.

    Raises:
        ValidationError: ``since`` is provided but not parseable as
            ISO-8601.
    """
    since_dt: datetime | None = None
    if since is not None and since.strip():
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise ValidationError("since must be ISO-8601") from exc
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=UTC)

    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = select(AgentRunOperation).order_by(AgentRunOperation.started_at.desc())
        if target is not None and target.strip():
            stmt = stmt.where(AgentRunOperation.target_table == target.strip())
        if errored:
            stmt = stmt.where(AgentRunOperation.error_message.is_not(None))
        if since_dt is not None:
            stmt = stmt.where(AgentRunOperation.started_at >= since_dt)
        stmt = stmt.limit(limit)
        for row in session.scalars(stmt).all():
            duration_ms: int | None = None
            if row.finished_at is not None and row.started_at is not None:
                duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
            try:
                params = json.loads(row.params_json)
            except json.JSONDecodeError:
                params = {}
            out.append(
                {
                    "id": row.id,
                    "agent_run_id": row.agent_run_id,
                    "ordinal": row.ordinal,
                    "op_name": row.op_name,
                    "params": params,
                    "target_table": row.target_table,
                    "rows_affected": row.rows_affected,
                    "delta_version_before": row.delta_version_before,
                    "delta_version_after": row.delta_version_after,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": (row.finished_at.isoformat() if row.finished_at else None),
                    "duration_ms": duration_ms,
                    "error_message": row.error_message,
                    "status": "error" if row.error_message else "ok",
                }
            )
    return {"operations": out}


@router.get("/api/agent-runs")
async def api_list_agent_runs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    principal: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
) -> dict[str, Any]:
    """List recent agent runs as JSON, optionally filtered.

    A companion to ``GET /runs`` for machine consumers (the Hermes
    plugin, curl probes, dashboards).  Ordered newest-first by
    ``started_at``.

    Optional ``principal`` / ``agent_id`` / ``status`` / ``since``
    filters back the Family-B ``pql_runs_by_principal`` and
    ``pql_runs_by_agent`` tools through a single backing route.
    Filters are AND-ed; missing filters fall through to "match all".

    Args:
        request: Incoming FastAPI request.
        limit: Maximum number of rows to return (1-500).
        principal: Exact-match filter on
            ``agent_runs.principal``.
        agent_id: Exact-match filter on ``agent_runs.agent_id``.
        status: Exact-match filter on ``agent_runs.status``.
        since: ISO-8601 lower bound on ``started_at``.

    Returns:
        ``{"runs": [...]}`` with each entry shaped by
        :func:`serialize_agent_run`.

    Raises:
        ValidationError: ``since`` is provided but not parseable as
            ISO-8601.
    """
    since_dt: datetime | None = None
    if since is not None and since.strip():
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise ValidationError("since must be ISO-8601") from exc
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=UTC)

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
        if principal is not None and principal.strip():
            stmt = stmt.where(AgentRun.principal == principal.strip())
        if agent_id is not None and agent_id.strip():
            stmt = stmt.where(AgentRun.agent_id == agent_id.strip())
        if status is not None and status.strip():
            stmt = stmt.where(AgentRun.status == status.strip())
        if since_dt is not None:
            stmt = stmt.where(AgentRun.started_at >= since_dt)
        rows = list(session.scalars(stmt).all())
        payload = [serialize_agent_run(r) for r in rows]
    return {"runs": payload}


def _summarize_run(
    run_row: AgentRun,
    operations: list[AgentRunOperation],
    tool_calls: list[AgentRunToolCall],
    queries: list[QueryHistory],
) -> dict[str, Any]:
    """Produce the Family-B risk-summary payload for one run.

    Pure helper — takes already-loaded ORM rows so the diff route
    can summarise both sides in one DB transaction.

    Args:
        run_row: The ``agent_runs`` row.
        operations: Per-run operation rows.
        tool_calls: Per-run LLM tool-call rows.
        queries: Per-run ``query_history`` rows.

    Returns:
        ``{rows_touched, delta_version_range, errored_ops_count,
        failing_ops, queries_count, tables_touched, status,
        has_denied_reason}``.  ``failing_ops`` is a list of the
        per-op detail rows (op_id, ordinal, op_name, target_table,
        error_message, started_at, finished_at) for every operation
        whose ``error_message`` is non-null.4 added this
        so the Incident-Responder agent can identify which op
        failed without a separate per-op fetch.  Deliberately omits
        ``cost_gate_threshold`` (Anti-gaming — agents shouldn't read
        the threshold they could be tuned to stay under).
    """
    tables_touched: list[str] = []
    if run_row.tables_touched:
        try:
            decoded: Any = json.loads(run_row.tables_touched)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            tables_touched = [
                str(item)  # pyright: ignore[reportUnknownArgumentType]
                for item in decoded  # pyright: ignore[reportUnknownVariableType]
            ]
    rows_touched = sum((op.rows_affected or 0) for op in operations)
    errored_ops_count = sum(1 for op in operations if op.error_message)
    #  bug-hunt: surface every errored op so the
    # Incident-Responder agent can name the failing op + its error
    # message without a separate per-op fetch.  Without this the
    # response only carried a count and the agent had no way to
    # answer "which op errored?".
    failing_ops: list[dict[str, Any]] = [
        {
            "op_id": op.id,
            "ordinal": op.ordinal,
            "op_name": op.op_name,
            "target_table": op.target_table,
            "error_message": op.error_message,
            "started_at": op.started_at.isoformat() if op.started_at else None,
            "finished_at": op.finished_at.isoformat() if op.finished_at else None,
        }
        for op in operations
        if op.error_message
    ]
    delta_version_range: dict[str, list[int | None]] = {}
    for op in operations:
        if op.target_table is None:
            continue
        bounds = delta_version_range.setdefault(
            op.target_table, [op.delta_version_before, op.delta_version_after]
        )
        if op.delta_version_before is not None:
            current_lo = bounds[0]
            if current_lo is None or op.delta_version_before < current_lo:
                bounds[0] = op.delta_version_before
        if op.delta_version_after is not None:
            current_hi = bounds[1]
            if current_hi is None or op.delta_version_after > current_hi:
                bounds[1] = op.delta_version_after
    return {
        "id": run_row.id,
        "status": run_row.status,
        "principal": run_row.principal,
        "agent_id": run_row.agent_id,
        "rows_touched": rows_touched,
        "errored_ops_count": errored_ops_count,
        "failing_ops": failing_ops,
        "operations_count": len(operations),
        "tool_calls_count": len(tool_calls),
        "queries_count": len(queries),
        "tables_touched": tables_touched,
        "delta_version_range": delta_version_range,
        "has_denied_reason": bool(run_row.denied_reason),
        "started_at": run_row.started_at.isoformat() if run_row.started_at else None,
        "finished_at": (run_row.finished_at.isoformat() if run_row.finished_at else None),
    }


def _load_run_summary_bundle(
    factory: Any, run_id: str
) -> tuple[AgentRun, list[AgentRunOperation], list[AgentRunToolCall], list[QueryHistory]]:
    """Load run + every per-run sibling needed for ``_summarize_run``.

    Args:
        factory: Sessionmaker callable from ``app.state``.
        run_id: UUID of the run to load.

    Returns:
        Tuple of detached ORM rows: run, operations, tool calls,
        query-history.

    Raises:
        CatalogNotFoundError: No agent run with that id.
    """
    with factory() as session:
        run_row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run_row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        operations = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == run_id)
                .order_by(AgentRunOperation.ordinal)
            ).all()
        )
        tool_calls = list(
            session.scalars(
                select(AgentRunToolCall)
                .where(AgentRunToolCall.agent_run_id == run_id)
                .order_by(AgentRunToolCall.called_at)
            ).all()
        )
        queries = list(
            session.scalars(
                select(QueryHistory)
                .where(QueryHistory.agent_run_id == run_id)
                .order_by(QueryHistory.started_at.desc())
            ).all()
        )
        for entity in (run_row, *operations, *tool_calls, *queries):
            session.expunge(entity)
    return run_row, operations, tool_calls, queries


@router.get("/api/agent-runs/{run_id}/summary")
async def api_agent_run_summary(request: Request, run_id: str) -> dict[str, Any]:
    """Risk-summary JSON for one run.  Supervisor scope required.

    Backs the ``pql_run_summary`` Hermes tool and is the per-side
    payload of the diff route below.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string from the URL.

    Returns:
        Dict shaped by :func:`_summarize_run`.
        :func:`require_supervisor` raises :class:`AuthorizationError`
        when the caller lacks the ``supervisor`` scope, and
        :func:`_load_run_summary_bundle` raises
        :class:`CatalogNotFoundError` when the run id is unknown.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    run_row, operations, tool_calls, queries = _load_run_summary_bundle(factory, run_id)
    return _summarize_run(run_row, operations, tool_calls, queries)


@router.get("/api/agent-runs/diff")
async def api_agent_runs_diff(
    request: Request,
    a: str = Query(..., description="UUID of run A"),
    b: str = Query(..., description="UUID of run B"),
    detail: bool = Query(default=False),
    align: str = Query(default="ordinal", pattern="^(ordinal|content)$"),
) -> dict[str, Any]:
    """Diff between two runs.  Supervisor scope required.

    The base response is a side-by-side summary diff; passing
    ``detail=true`` extends it with an op-by-op + tool-call-by-
    tool-call diff (see
    :func:`pointlessql.services.run_diff.build_detail_diff` for
    the alignment strategies).

    Args:
        request: Incoming FastAPI request.
        a: Run UUID for the left side of the comparison.
        b: Run UUID for the right side.
        detail: When ``True``, the response also carries
            ``operations_diff`` + ``tool_calls_diff``.
        align: ``"ordinal"`` (default — pair by index) or
            ``"content"`` (greedy match on op_name/target_table).

    Returns:
        Always ``{a_summary, b_summary, ops_count_diff,
        tool_calls_count_diff, queries_count_diff, rows_touched_diff,
        errored_ops_diff, tables_only_in_a, tables_only_in_b,
        tables_in_both, status_diff}``.  When ``detail=True`` adds
        ``operations_diff``, ``tool_calls_diff``, ``align``,
        ``truncated``.

        :func:`require_supervisor` raises :class:`AuthorizationError`
        when the caller lacks the ``supervisor`` scope;
        :func:`_load_run_summary_bundle` raises
        :class:`CatalogNotFoundError` when either run id is unknown.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    run_a, ops_a, tcs_a, qs_a = _load_run_summary_bundle(factory, a)
    run_b, ops_b, tcs_b, qs_b = _load_run_summary_bundle(factory, b)
    summary_a = _summarize_run(run_a, ops_a, tcs_a, qs_a)
    summary_b = _summarize_run(run_b, ops_b, tcs_b, qs_b)
    tables_a = set(summary_a["tables_touched"])
    tables_b = set(summary_b["tables_touched"])
    payload: dict[str, Any] = {
        "a_summary": summary_a,
        "b_summary": summary_b,
        "ops_count_diff": summary_b["operations_count"] - summary_a["operations_count"],
        "tool_calls_count_diff": summary_b["tool_calls_count"] - summary_a["tool_calls_count"],
        "queries_count_diff": summary_b["queries_count"] - summary_a["queries_count"],
        "rows_touched_diff": summary_b["rows_touched"] - summary_a["rows_touched"],
        "errored_ops_diff": summary_b["errored_ops_count"] - summary_a["errored_ops_count"],
        "tables_only_in_a": sorted(tables_a - tables_b),
        "tables_only_in_b": sorted(tables_b - tables_a),
        "tables_in_both": sorted(tables_a & tables_b),
        "status_diff": {"a": summary_a["status"], "b": summary_b["status"]},
    }
    if detail:
        # FastAPI Query(pattern=…) already constrains align; cast
        # to the typed alias for the service signature.
        align_mode: AlignmentMode = "content" if align == "content" else "ordinal"
        payload.update(
            build_detail_diff(
                ops_a=ops_a,
                ops_b=ops_b,
                tool_calls_a=tcs_a,
                tool_calls_b=tcs_b,
                align=align_mode,
            )
        )
        payload["lineage_diff"] = build_lineage_diff(
            factory,
            run_a_id=a,
            run_b_id=b,
        )
    return payload


@router.post("/api/agent-runs/{run_id}/approve")
async def api_approve_agent_run(
    request: Request,
    run_id: str,
) -> dict[str, Any]:
    """Admin-only approval for a run pending ``needs_approval``.

    Transitions the row to ``approved`` and records the approving
    admin + timestamp.  The HTML supervision UI surfaces this as an
    Approve button on the run-detail page.

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
            raise ValidationError(f"agent run {run_id!r} is {row.status!r}, cannot approve")
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
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(default={}),
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
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) and reason_raw.strip() else None
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status != "needs_approval":
            raise ValidationError(f"agent run {run_id!r} is {row.status!r}, cannot deny")
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
    """Record one LLM tool invocation against an agent run.

    The Hermes plugin's ``post_tool_call`` hook posts here for any
    tool whose name starts with ``pql_``.  Persists the row in
    ``agent_run_tool_calls`` and emits a
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
            raise ValidationError("called_at must be ISO-8601 when provided") from exc
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=UTC)
    else:
        called_at = datetime.now(UTC)

    factory = request.app.state.session_factory
    with factory() as session:
        run_row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
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
    await emit_agent_run_event(EVENT_TYPE_TOOL_CALL, payload, session_factory=factory)
    return payload


def _record_audit_self(
    request: Request,
    *,
    endpoint: str,
    params: dict[str, Any],
    started_at: datetime,
) -> None:
    """Persist a ``query_history`` row for one ``/api/agent-runs/.../audit/*`` call.

     audit-of-audit logging — every per-run audit-axis
    read leaves a ``read_kind='audit_api'`` breadcrumb so the
    cockpit/Hermes traffic stays visible in the same audit lake it
    queries.  Best-effort: a swallowed insert never fails the actual
    audit response (the agent reviewing yesterday's anomalies needs
    the data more than it needs a self-tracking row).

    Args:
        request: FastAPI request, carrying the authenticated user.
        endpoint: Stable string identifier for the route, e.g.
            ``"/api/agent-runs/{run_id}/audit/lineage"``.
        params: Query-string params honoured (so a "weirdly empty
            result" can be re-traced via the params the cockpit
            caller actually sent).
        started_at: Wall-clock instant the route began handling.
    """
    user = get_user(request)
    finished_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    sql_text = f"-- audit_api: {endpoint} {json.dumps(params, sort_keys=True, default=str)}"
    try:
        record_query(
            factory,
            user_id=int(user.get("id") or 0),
            user_email=str(user.get("email") or "anonymous"),
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status="succeeded",
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[],
            agent_run_id=None,
            read_kind="audit_api",
        )
    except Exception as exc:  # noqa: BLE001 — audit-of-audit must never break the audit response
        logger.warning("audit_api: failed to self-track %s: %s", endpoint, exc)


def _ensure_run_visible(factory: Any, run_id: str) -> AgentRun:
    """Return the ``AgentRun`` row for *run_id* or raise 404.

    Shared 404-guard for the per-run audit-axis endpoints so a
    Hermes audit-reviewer that cites a stale ``run_id`` gets a
    clean ``CatalogNotFoundError`` rather than a hollow ``rows: []``.

    Args:
        factory: Sessionmaker callable from ``app.state``.
        run_id: UUID of the run to load.

    Returns:
        Detached :class:`AgentRun` row.

    Raises:
        CatalogNotFoundError: No run with that id.
    """
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        session.expunge(row)
    return row


@router.get("/api/agent-runs/{run_id}/audit/lineage")
async def api_agent_run_audit_lineage(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to a single op's edges"),
) -> dict[str, Any]:
    """Return :class:`LineageRowEdge` aggregates per op for one run.

    JSON sibling to the run-detail Lineage tab,
    consumed by the new ``pql_query_row_lineage``-style Hermes
    tools.  Calls into :func:`runs_routes.load_lineage_summary_for_run`
    so the SQL stays in one place.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional cross-axis filter — restrict aggregate to a
            single op.  Stale ids fall back to "no rows".

    Returns:
        ``{"run_id", "op_id", "total_edges", "rows": [...]}`` (rows
        carry ``ordinal``/``op_name``/``source_table``/``target_table``/
        ``edge_count``).

    Raises:
        AuthorizationError: When the caller lacks the supervisor or
            auditor scope.
        CatalogNotFoundError: When no run with that id exists.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    _ensure_run_visible(factory, run_id)
    from pointlessql.api.runs_routes import load_lineage_summary_for_run

    payload = load_lineage_summary_for_run(request, run_id, op_id=op_id)
    response = {"run_id": run_id, "op_id": op_id, **payload}
    _record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/lineage",
        params={"run_id": run_id, "op_id": op_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/rejects")
async def api_agent_run_audit_rejects(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to one op's rejects"),
) -> dict[str, Any]:
    """Return :class:`LineageRowReject` rows for one run as JSON.

    wraps :func:`runs_routes.load_rejects_for_run`.
    Reject reasons are stored verbatim in the DB; PII handling is
    the caller's problem (PointlesSQL doesn't mask rejects today).

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional filter — restrict to a single op.

    Returns:
        ``{"run_id", "op_id", "row_count", "rows": [...]}`` (rows
        carry ``op_id``/``source_table``/``source_row_id``/``reason``/
        ``detail``/``created_at``).

    Raises:
        AuthorizationError: When the caller lacks the supervisor or
            auditor scope.
        CatalogNotFoundError: When no run with that id exists.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    _ensure_run_visible(factory, run_id)
    from pointlessql.api.runs_routes import load_rejects_for_run

    rows = load_rejects_for_run(request, run_id, op_id=op_id)
    serialised = [
        {
            **{k: v for k, v in row.items() if k != "created_at"},
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]
    response = {
        "run_id": run_id,
        "op_id": op_id,
        "row_count": len(serialised),
        "rows": serialised,
    }
    _record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/rejects",
        params={"run_id": run_id, "op_id": op_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/value-changes")
async def api_agent_run_audit_value_changes(
    request: Request,
    run_id: str,
    table: str | None = Query(default=None, description="Restrict to a target table FQN"),
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
    limit: int = Query(default=200, ge=1, le=1000),
    mask: bool = Query(
        default=True,
        description="Mask reversible cell values; admin-only PII reveal at /api/audit/pii/reveal",
    ),
) -> dict[str, Any]:
    """Return :class:`LineageValueChange` rows for one run.

    value-axis JSON view.  By default all
    ``old_value`` / ``new_value`` cells are masked at the API
    boundary; un-masking still requires admin via
    :func:`api_audit_pii_reveal`.  This keeps an auditor-key bound
    Hermes flow from inadvertently echoing reversible cleartext into
    a webhook.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        table: Optional target-table filter (three-part UC name).
        op_id: Optional op filter.
        limit: Hard row cap (1–1000).
        mask: When ``True`` (default), ``old_value`` / ``new_value``
            are replaced with ``"***"`` placeholders.  When
            ``False``, the API still strips both values to ``None``
            and surfaces only the row-level metadata — auditor scope
            does not authorise cleartext, period.  ``mask=false``
            is honoured only for the cookie-authenticated admin.

    Returns:
        ``{"run_id", "table", "op_id", "row_count", "masked": bool,
        "rows": [...]}``.

    Raises:
        AuthorizationError: When the caller lacks the supervisor or
            auditor scope.
        CatalogNotFoundError: When no run with that id exists.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    _ensure_run_visible(factory, run_id)
    user = get_user(request)
    cleartext_authorised = bool(user.get("is_admin")) and not mask
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageValueChange)
            .where(LineageValueChange.run_id == run_id)
            .order_by(LineageValueChange.id)
            .limit(limit)
        )
        if table is not None and table.strip():
            stmt = stmt.where(LineageValueChange.target_table == table.strip())
        if op_id is not None:
            stmt = stmt.where(LineageValueChange.op_id == op_id)
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "target_table": r.target_table,
                    "target_row_id": r.target_row_id,
                    "target_column": r.target_column,
                    "old_value": r.old_value if cleartext_authorised else None,
                    "new_value": r.new_value if cleartext_authorised else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    response = {
        "run_id": run_id,
        "table": table,
        "op_id": op_id,
        "row_count": len(rows),
        "masked": not cleartext_authorised,
        "rows": rows,
    }
    _record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/value-changes",
        params={"run_id": run_id, "table": table, "op_id": op_id, "limit": limit, "mask": mask},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/external-writes")
async def api_agent_run_audit_external_writes(
    request: Request,
    run_id: str,
) -> dict[str, Any]:
    """Return ``unattributed_writes`` rows touching this run's tables.

    JSON over the existing
    :func:`runs_routes.load_unattributed_for_run` helper.  Filters
    to the tables the run actually touched (via
    ``AgentRun.tables_touched`` JSON) and to unacknowledged rows
    so the response mirrors the run-detail "External writes" tab.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.

    Returns:
        ``{"run_id", "tables_touched", "row_count", "rows": [...]}``.

    Raises:
        AuthorizationError: When the caller lacks the supervisor or
            auditor scope.
        CatalogNotFoundError: When no run with that id exists.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    run_row = _ensure_run_visible(factory, run_id)
    tables_touched: list[str] = []
    if run_row.tables_touched:
        try:
            decoded: Any = json.loads(run_row.tables_touched)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            tables_touched = [
                str(t)  # pyright: ignore[reportUnknownArgumentType]
                for t in decoded  # pyright: ignore[reportUnknownVariableType]
            ]
    from pointlessql.api.runs_routes import load_unattributed_for_run

    rows = load_unattributed_for_run(request, tables_touched=tables_touched)
    response = {
        "run_id": run_id,
        "tables_touched": tables_touched,
        "row_count": len(rows),
        "rows": rows,
    }
    _record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/external-writes",
        params={"run_id": run_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/column-lineage")
async def api_agent_run_audit_column_lineage(
    request: Request,
    run_id: str,
    table: str | None = Query(default=None, description="Restrict to a target table FQN"),
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
) -> dict[str, Any]:
    """Return :class:`LineageColumnMap` rows for one run.

    column-axis JSON view.  Powers the
    ``pql_query_column_lineage`` Hermes tool and is the backing
    surface the run-detail column-trace links also call.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        table: Optional target-table filter (three-part UC name).
        op_id: Optional op filter.

    Returns:
        ``{"run_id", "table", "op_id", "row_count", "rows": [...]}``
        with rows shaped ``{"op_id", "source_table", "source_column",
        "target_table", "target_column", "transform_kind",
        "transform_detail"}``.

    Raises:
        AuthorizationError: When the caller lacks the supervisor or
            auditor scope.
        CatalogNotFoundError: When no run with that id exists.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    _ensure_run_visible(factory, run_id)
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageColumnMap)
            .where(LineageColumnMap.run_id == run_id)
            .order_by(LineageColumnMap.id)
        )
        if table is not None and table.strip():
            stmt = stmt.where(LineageColumnMap.target_table == table.strip())
        if op_id is not None:
            stmt = stmt.where(LineageColumnMap.op_id == op_id)
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "source_table": r.source_table,
                    "source_column": r.source_column,
                    "target_table": r.target_table,
                    "target_column": r.target_column,
                    "transform_kind": r.transform_kind,
                    "transform_detail": r.transform_detail,
                }
            )
    response = {
        "run_id": run_id,
        "table": table,
        "op_id": op_id,
        "row_count": len(rows),
        "rows": rows,
    }
    _record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/column-lineage",
        params={"run_id": run_id, "table": table, "op_id": op_id},
        started_at=started_at,
    )
    return response


__all__ = ["router", "serialize_agent_run"]
