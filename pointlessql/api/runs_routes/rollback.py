"""Run-rollback routes — preview + execute + supporting helpers.

Two HTTP-facing endpoints:

* ``GET /api/runs/{run_id}/rollback-preview`` — what would happen
  if we restored the targeted op's pre-write Delta version, plus a
  staleness flag and a downstream-warning list.
* ``POST /api/runs/{run_id}/rollback`` — actually execute it under a
  freshly-spawned ``agent_runs`` row so the audit trail records the
  attempt and outcome distinctly from the original run.

Both routes are admin-only.  The eight private helpers in this
module own the rollback-specific concerns (Delta version reads,
intervening-write detection, target-table discovery, and the
mapping from refusal exception classes to PointlesSQL HTTP errors).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.config import Settings
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services._executor import run_sync
from pointlessql.services.agent_runs.events import (
    EVENT_TYPE_ROLLBACK_EXECUTED,
    emit_agent_run_event,
)
from pointlessql.services.agent_runs.operations import (
    RollbackAmbiguous,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)
from pointlessql.services.workspace import find_downstream_tables
from pointlessql.types import OpName

router = APIRouter()


def rollback_targets_for_run(request: Request, run_id: str) -> list[str]:
    """Return de-duplicated ``target_table`` names this run wrote to.

    Drives the Rollback dropdown menu in ``run_view.html``.  Only
    write-shaped op names contribute (``merge`` / ``write_table`` /
    ``autoload`` / ``aggregate``); ``sql`` and prior ``rollback``
    ops are excluded so the menu doesn't offer to rollback a read
    or a rollback (rollback-of-rollback is technically possible but
    the v1 UX leaves it to direct API calls).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Sorted list of distinct target table FQNs.  Empty when the
        run wrote nothing (notebook ran only ``pql.sql`` reads).
    """
    write_ops = ("merge", "write_table", "autoload", "aggregate")
    factory = request.app.state.session_factory
    targets: set[str] = set()
    with factory() as session:
        rows = session.scalars(
            select(AgentRunOperation.target_table)
            .where(AgentRunOperation.agent_run_id == run_id)
            .where(AgentRunOperation.op_name.in_(write_ops))
            .where(AgentRunOperation.target_table.is_not(None))
        )
        for value in rows:
            if value:
                targets.add(value)
    return sorted(targets)


def _serialize_op_candidate(row: AgentRunOperation) -> dict[str, Any]:
    """Project the columns the rollback-preview UI needs from an op row."""
    return {
        "id": row.id,
        "ordinal": row.ordinal,
        "op_name": row.op_name,
        "delta_version_before": row.delta_version_before,
        "delta_version_after": row.delta_version_after,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


async def _read_delta_version(request: Request, target: str) -> int | None:
    """Read ``DeltaTable.version()`` for *target*, best-effort.

    The preview-render path reaches into Delta to compare the
    targeted op's recorded ``delta_version_after`` to "right now".
    A read failure (table missing, soyuz down) returns ``None`` so
    the modal renders ``"current version: unknown"`` instead of a
    500.

    Args:
        request: Incoming FastAPI request — provides the UC client.
        target: Fully-qualified UC table name.

    Returns:
        The current Delta version, or ``None`` when the version
        couldn't be read.
    """
    try:
        client = get_uc_client(request)
        parts = target.split(".")
        if len(parts) != 3:
            return None
        info = await client.get_table(parts[0], parts[1], parts[2])
        if not info:
            return None
        location = info.get("storage_location")
        if not isinstance(location, str) or not location:
            return None
        from pointlessql.pql import safe_delta_version

        return safe_delta_version(location)
    except Exception:  # noqa: BLE001 — preview route is best-effort
        # bare-broad-ok: preview returns None on Delta-history hiccup
        return None


def _load_intervening_writes(
    request: Request,
    *,
    target: str,
    after_version: int,
    exclude_run: str,
) -> list[dict[str, Any]]:
    """Return ``agent_run_operations`` rows that wrote *target* after *after_version*.

    Drives the ⚠ stale-warning panel.  The exclusion is by run id —
    other ops within the same run that share the target ordinal are
    surfaced as ``op_candidates``, not as intervening writes.

    Args:
        request: Incoming FastAPI request — provides the session
            factory.
        target: ``target_table`` to scope the search to.
        after_version: ``delta_version_after`` of the targeted op;
            rows with a strictly greater value are intervening.
        exclude_run: ``agent_run_id`` of the run being rolled back.

    Returns:
        A list of dicts shaped like ``{"run_id", "op_id",
        "delta_version_after", "started_at"}``, ordered by
        ``delta_version_after`` ascending.  Empty when no rows
        match (or the query failed — best-effort).
    """
    factory = request.app.state.session_factory
    try:
        with factory() as session:
            rows = list(
                session.scalars(
                    select(AgentRunOperation)
                    .where(AgentRunOperation.target_table == target)
                    .where(AgentRunOperation.delta_version_after > after_version)
                    .where(AgentRunOperation.agent_run_id != exclude_run)
                    .order_by(AgentRunOperation.delta_version_after)
                )
            )
            return [
                {
                    "run_id": row.agent_run_id,
                    "op_id": row.id,
                    "delta_version_after": row.delta_version_after,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                }
                for row in rows
            ]
    except Exception:  # noqa: BLE001 — preview is best-effort
        # bare-broad-ok: intervening-writes panel renders empty on DB hiccup
        return []


@router.get("/api/runs/{run_id}/rollback-preview")
async def api_rollback_preview(
    request: Request,
    run_id: str,
    target: str = Query(description="UC catalog.schema.table to preview rollback for"),
) -> dict[str, Any]:
    """Preview what ``pql.rollback`` would do for ``(run_id, target)``.

    Returns the version delta that would be restored, a flag for
    whether the table moved past the targeted op (staleness),
    a list of intervening ``agent_run_operations`` rows that would
    be overwritten on a forced rollback, and a list of downstream
    tables that derived data from the target via row + column
    lineage.  When the run touched the target more than once the
    response carries ``op_candidates`` and ``op_id: null`` so the
    caller can pick by ordinal.

    The route is admin-only — rollback itself is admin-only and the
    preview leaks no information beyond what the admin can already
    see in ``/runs/{id}``.  Propagates :class:`AuthorizationError`
    raised by ``require_admin`` for non-admin callers.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the run whose write is being
            previewed.
        target: Fully-qualified UC name of the target table.

    Returns:
        ``{"run_id", "target_table", "op_id", "op_candidates",
        "delta_version_before", "delta_version_after",
        "current_version", "is_stale", "intervening_writes",
        "downstream_warnings"}``.

    Raises:
        CatalogNotFoundError: No matching ``agent_run_operations``
            row, or the target is unknown to soyuz-catalog.
        ValidationError: The targeted op is a creation
            (``delta_version_before is None``) and rollback would
            mean dropping the table (out of v1 scope).
    """
    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == run_id)
                .where(AgentRunOperation.target_table == target)
                .order_by(AgentRunOperation.ordinal)
            )
        )
        for row in rows:
            session.expunge(row)
    if not rows:
        raise CatalogNotFoundError(f"agent run {run_id!r} did not write to {target!r}")

    op_candidates = [_serialize_op_candidate(row) for row in rows]

    chosen: AgentRunOperation | None = rows[0] if len(rows) == 1 else None

    intervening: list[dict[str, Any]] = []
    current_version: int | None = None
    is_stale: bool = False

    if chosen is not None:
        if chosen.delta_version_before is None:
            raise ValidationError(
                f"agent run {run_id!r} created {target!r} (delta_version_before is None); "
                "rollback would mean dropping the table (out of v1 scope)"
            )
        current_version = await _read_delta_version(request, target)
        if (
            current_version is not None
            and chosen.delta_version_after is not None
            and current_version != chosen.delta_version_after
        ):
            is_stale = True
            intervening = _load_intervening_writes(
                request,
                target=target,
                after_version=chosen.delta_version_after,
                exclude_run=run_id,
            )

    downstream_warnings = [
        {
            "target_table": spec.target_table,
            "via": spec.via,
            "edge_count": spec.edge_count,
            "most_recent_run_id": spec.most_recent_run_id,
        }
        for spec in find_downstream_tables(factory, source_table=target)
    ]

    return {
        "run_id": run_id,
        "target_table": target,
        "op_id": chosen.id if chosen is not None else None,
        "op_candidates": op_candidates,
        "delta_version_before": chosen.delta_version_before if chosen is not None else None,
        "delta_version_after": chosen.delta_version_after if chosen is not None else None,
        "current_version": current_version,
        "is_stale": is_stale,
        "intervening_writes": intervening,
        "downstream_warnings": downstream_warnings,
    }


def _mark_rollback_run_failed(
    factory: Any,
    *,
    run_id: str,
    message: str,
) -> None:
    """Mark the spawned rollback run as ``failed`` on a refusal.

    Always best-effort — the route is about to re-raise, so a DB
    error here gets swallowed rather than masking the underlying
    rollback exception.

    Args:
        factory: SQLAlchemy session factory.
        run_id: Newly-created ``agent_runs.id`` for the rollback.
        message: Short summary stored on
            ``agent_runs.denied_reason``.
    """
    finished_at = datetime.datetime.now(datetime.UTC)
    try:
        with factory() as session:
            row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if row is None:
                return
            row.status = "failed"
            row.finished_at = finished_at
            row.denied_reason = message[:500]
            session.commit()
    except Exception:  # noqa: BLE001 — best-effort run-marker
        # bare-broad-ok: failure of failure-marker write is silent on purpose
        return


def _finalise_rollback_run(
    factory: Any,
    *,
    run_id: str,
    finished_at: datetime.datetime,
) -> int | None:
    """Mark the rollback run ``succeeded`` and return its op id.

    Reads the single ``agent_run_operations`` row the rollback
    primitive emitted (one rollback = one op).  ``None`` is
    returned when no op landed (shouldn't happen on the success
    path, but defensive in case the recorder failed silently).

    Args:
        factory: SQLAlchemy session factory.
        run_id: Newly-created rollback run id.
        finished_at: UTC instant the rollback completed.

    Returns:
        The ``agent_run_operations.id`` for the rollback op, or
        ``None`` when no op exists.
    """
    op_id: int | None = None
    with factory() as session:
        op = session.scalar(
            select(AgentRunOperation)
            .where(AgentRunOperation.agent_run_id == run_id)
            .where(AgentRunOperation.op_name == OpName.ROLLBACK)
            .order_by(AgentRunOperation.ordinal.desc())
            .limit(1)
        )
        if op is not None:
            op_id = op.id
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is not None:
            row.status = "succeeded"
            row.finished_at = finished_at
            session.commit()
    return op_id


@router.post("/api/runs/{run_id}/rollback")
async def api_run_rollback(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Execute ``pql.rollback`` for ``(run_id, target)`` under a fresh run.

    Spawns a brand-new ``agent_runs`` row to host the rollback op,
    invokes :func:`pointlessql.pql._rollback.rollback_table` under
    that run id, and returns the new run id + the version delta on
    success.  Refusal modes from the primitive each carry their own
    HTTP status + error code via the centralised handler:

    * ``RollbackTargetNotFound`` → 404 ``rollback_target_not_found``.
    * ``RollbackAmbiguous`` → 409 ``rollback_ambiguous`` with
      ``candidate_ordinals`` extension payload.
    * ``RollbackInvalid`` → 422 ``rollback_invalid``.
    * ``RollbackStale`` → 409 ``rollback_stale`` with
      ``current_version`` / ``expected_version`` /
      ``intervening_op_count`` extension payload.

    On any refusal the spawned rollback run is marked ``failed``
    with ``finished_at`` set so the audit trail records both the
    attempt and the gate that fired.

    A ``pointlessql.rollback.executed`` CloudEvent fires on
    success; the same event family the rest of agent-run lifecycle
    uses.

    Propagates :class:`AuthorizationError` raised by
    ``require_admin`` for non-admin callers.

    Args:
        request: Incoming FastAPI request.
        run_id: ``agent_runs.id`` whose write should be undone.
        body: JSON body with ``target`` (3-part UC name, required),
            ``op_ordinal`` (int, optional — required when the run
            touched the target more than once), ``allow_force``
            (bool, default ``False``).

    Returns:
        ``{"new_run_id", "new_op_id", "version_before",
        "version_after", "target_version_restored",
        "rolled_back_run_id", "target", "allow_force"}``.

    Raises:
        ValidationError: Body shape problem (missing ``target``,
            non-integer ``op_ordinal``).
        RollbackTargetNotFound: The run never wrote to ``target``,
            or the target isn't registered with soyuz.
        RollbackAmbiguous: The run touched the target more than
            once and no ``op_ordinal`` disambiguates.
        RollbackInvalid: The targeted op was a creation (drop is
            out of scope for rollback).
        RollbackStale: The table moved past the targeted op and
            ``allow_force`` was not set.
        Exception: Any unexpected primitive failure is re-raised
            after the spawned rollback run is marked ``failed``.
    """
    require_admin(request)

    target = body.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a 3-part UC name")
    op_ordinal_raw = body.get("op_ordinal")
    op_ordinal: int | None
    if op_ordinal_raw is None:
        op_ordinal = None
    elif isinstance(op_ordinal_raw, int):
        op_ordinal = op_ordinal_raw
    else:
        raise ValidationError("op_ordinal must be an integer or null")
    allow_force = bool(body.get("allow_force", False))

    factory = request.app.state.session_factory
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")

    new_run_id = str(uuid.uuid4())
    started_at = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        rollback_run = AgentRun(
            id=new_run_id,
            principal=principal or None,
            agent_id="pointlessql.rollback",
            notebook_path=f"rollback-of-{run_id}",
            status="running",
            started_at=started_at,
        )
        session.add(rollback_run)
        session.commit()

    settings: Settings = request.app.state.settings

    def _run_rollback() -> dict[str, Any]:
        from pointlessql.pql import PQL  # noqa: PLC0415 — lazy

        pql = PQL(
            settings=settings,
            principal=principal or None,
            agent_run_id=new_run_id,
        )
        result = pql.rollback(
            target,
            before_run=run_id,
            op_ordinal=op_ordinal,
            allow_force=allow_force,
        )
        return {
            "version_before": result.version_before,
            "version_after": result.version_after,
            "target_version_restored": result.target_version_restored,
            "restored_file_count": result.restored_file_count,
        }

    try:
        result = await run_sync(_run_rollback)
    except (RollbackAmbiguous, RollbackStale, RollbackInvalid, RollbackTargetNotFound) as exc:
        # Each refusal class is now a PointlessSQLError subclass with
        # its own status_code / error_code; the centralised handler
        # picks them up directly. We only need to mark the spawned
        # rollback run as failed before re-raising.
        _mark_rollback_run_failed(factory, run_id=new_run_id, message=repr(exc))
        raise
    except Exception:
        _mark_rollback_run_failed(factory, run_id=new_run_id, message="rollback raised")
        raise

    finished_at = datetime.datetime.now(datetime.UTC)
    new_op_id = _finalise_rollback_run(
        factory,
        run_id=new_run_id,
        finished_at=finished_at,
    )

    payload = {
        "new_run_id": new_run_id,
        "new_op_id": new_op_id,
        "version_before": result["version_before"],
        "version_after": result["version_after"],
        "target_version_restored": result["target_version_restored"],
        "restored_file_count": result["restored_file_count"],
        "rolled_back_run_id": run_id,
        "target": target,
        "allow_force": allow_force,
    }

    await audit(
        request,
        "rollback_run",
        f"agent_run:{run_id}",
        {
            "target": target,
            "new_run_id": new_run_id,
            "version_before": result["version_before"],
            "version_after": result["version_after"],
            "allow_force": allow_force,
        },
    )

    await emit_agent_run_event(
        EVENT_TYPE_ROLLBACK_EXECUTED,
        {
            "id": new_run_id,
            "rolled_back_run_id": run_id,
            "target_table": target,
            "version_before": result["version_before"],
            "version_after": result["version_after"],
            "target_version_restored": result["target_version_restored"],
            "new_op_id": new_op_id,
            "allow_force": allow_force,
        },
        session_factory=factory,
    )

    return payload
