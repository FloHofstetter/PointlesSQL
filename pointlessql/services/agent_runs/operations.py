"""Strict per-operation trail for agent runs.

Every PQL primitive call inside an agent run emits one row into the
``agent_run_operations`` table.  This module provides the helper
:func:`record_operation` plus a context-manager
:func:`operation_context` that primitives wrap their work in.

The mode is **strict**: if the trail row cannot be persisted (DB
down, FK miss because the run id is unknown to the registry), the
primitive raises :class:`pointlessql.exceptions.AuditUnavailableError`
*before* touching DuckDB or deltalake.  The contract is "no write
without a trail"; best-effort would defeat the forced-audit
guarantee.

Ordinal allocation is a SELECT-MAX-then-INSERT inside one
transaction.  SQLite's default WAL + serialised writers make this
race-safe enough for one-runtime-per-run; for parallel writers
within the same run, switch to a server-side
``COALESCE(MAX(ordinal), 0) + 1`` UPDATE/INSERT pattern.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models import AgentRun, AgentRunOperation

_LINEAGE_FAILED_MARKER = "[lineage_emit_failed]"

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


VALID_OP_NAMES = frozenset({"autoload", "merge", "write_table", "sql"})


@dataclass
class OperationRecorder:
    """Mutable state collected by a primitive while running.

    Primitives set the fields they know about on this recorder;
    :func:`operation_context` reads them at exit-time and writes the
    final ``agent_run_operations`` row.  Attribute setters are
    plain — the primitive's own logic is in charge of deciding
    whether a value applies (e.g. ``delta_version_before`` is only
    meaningful when the table existed).

    Attributes:
        input_sha: SHA-256 hex of the canonical Arrow IPC bytes (for
            writes / merges) or the concat-of-file-shas (for
            autoload).  ``None`` for read-only ``sql``.
        rows_affected: Row count produced by the primitive, or
            ``None`` when the primitive can't expose one.
        delta_version_before: ``DeltaTable.version()`` *before* the
            write, or ``None`` for new tables / read-only ops.
        delta_version_after: ``DeltaTable.version()`` *after* the
            write.
        target_table: Override for the value passed to
            :func:`operation_context` (autoload may discover the
            target's true URI mid-call).
        extra_params: Dict merged into ``params_json`` so the
            primitive can attach run-time stats (file counts, merge
            stats) without rebuilding the params dict.
    """

    input_sha: str | None = None
    rows_affected: int | None = None
    delta_version_before: int | None = None
    delta_version_after: int | None = None
    target_table: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)


def record_operation(
    session_factory: sessionmaker[Session],
    *,
    agent_run_id: str,
    op_name: str,
    params: dict[str, Any],
    target_table: str | None,
    input_sha: str | None,
    rows_affected: int | None,
    delta_version_before: int | None,
    delta_version_after: int | None,
    started_at: datetime.datetime,
    finished_at: datetime.datetime | None,
    error_message: str | None,
) -> int:
    """Insert one ``agent_run_operations`` row in strict mode.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_run_id: UUID string of the owning :class:`AgentRun`.
            Must already exist in the registry (FK enforced).
        op_name: One of :data:`VALID_OP_NAMES`.
        params: Aufruf-shape, JSON-encoded into ``params_json``.
        target_table: ``catalog.schema.table`` or ``None``.
        input_sha: 64-char hex digest or ``None``.
        rows_affected: Integer or ``None``.
        delta_version_before: Integer or ``None``.
        delta_version_after: Integer or ``None``.
        started_at: Wall-clock instant the primitive entered.
        finished_at: Wall-clock instant the primitive exited, or
            ``None`` when the row represents a still-in-flight call.
        error_message: ``repr(exc)`` on failure, ``None`` on success.

    Returns:
        The auto-assigned primary key.

    Raises:
        AuditUnavailableError: When the registry-side run does not
            exist, ``op_name`` is unknown, or any DB error blocks
            the insert.  The caller (a PQL primitive) MUST surface
            this and refuse to do its work.
    """
    if op_name not in VALID_OP_NAMES:
        raise AuditUnavailableError(f"agent_run_operations: unknown op_name {op_name!r}")

    try:
        with session_factory() as session:
            run_exists = session.scalar(select(AgentRun.id).where(AgentRun.id == agent_run_id))
            if run_exists is None:
                raise AuditUnavailableError(
                    f"agent_run_operations: agent_run_id {agent_run_id!r} is not registered"
                )
            next_ordinal = (
                session.scalar(
                    select(func.coalesce(func.max(AgentRunOperation.ordinal), 0)).where(
                        AgentRunOperation.agent_run_id == agent_run_id
                    )
                )
                or 0
            ) + 1
            row = AgentRunOperation(
                agent_run_id=agent_run_id,
                ordinal=next_ordinal,
                op_name=op_name,
                params_json=json.dumps(params, sort_keys=True, default=str),
                target_table=target_table,
                input_sha=input_sha,
                rows_affected=rows_affected,
                delta_version_before=delta_version_before,
                delta_version_after=delta_version_after,
                started_at=started_at,
                finished_at=finished_at,
                error_message=error_message,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
    except AuditUnavailableError:
        raise
    except SQLAlchemyError as exc:
        raise AuditUnavailableError(
            f"agent_run_operations: insert failed for run {agent_run_id!r}: {exc}"
        ) from exc


@contextmanager
def operation_context(
    session_factory: sessionmaker[Session] | None,
    *,
    agent_run_id: str | None,
    op_name: str,
    params: dict[str, Any],
    target_table: str | None = None,
) -> Iterator[OperationRecorder]:
    """Wrap a primitive call so a row is always emitted.

    Pre-flight: verifies the run exists by calling
    :func:`record_operation` would (we lazy-check at exit-time
    instead — the recorder yields immediately so primitives don't
    pay an extra round-trip).  At exit-time the recorder's collected
    state plus ``error_message`` (if the ``with`` body raised) is
    persisted.

    When ``agent_run_id`` is ``None`` the helper is a passthrough —
    the recorder yields, no row is written and ``session_factory``
    is unused.  This is the interactive-PQL path (no env var, no
    kwarg).

    Args:
        session_factory: SQLAlchemy session factory.  May be
            ``None`` if and only if ``agent_run_id`` is ``None``.
        agent_run_id: Run UUID or ``None`` to skip emission.
        op_name: One of :data:`VALID_OP_NAMES`.
        params: Initial params dict; the recorder's ``extra_params``
            is merged in at the end.
        target_table: Initial target.  Recorder may override.

    Yields:
        :class:`OperationRecorder` the primitive sets fields on.

    Raises:
        AuditUnavailableError: When emission is requested
            (``agent_run_id`` is set) and the trail row cannot be
            persisted.  Also re-raises whatever the wrapped block
            raised after persisting the failure row.
    """  # noqa: DOC502,DOC503 — re-raises wrapped exceptions verbatim
    recorder = OperationRecorder()
    if agent_run_id is None:
        yield recorder
        return

    if session_factory is None:
        raise AuditUnavailableError(
            f"operation_context: session_factory is None for run {agent_run_id!r}"
        )

    started_at = datetime.datetime.now(datetime.UTC)
    error_message: str | None = None
    try:
        yield recorder
    except BaseException as exc:  # noqa: BLE001 — record then re-raise
        error_message = repr(exc)
        finished_at = datetime.datetime.now(datetime.UTC)
        merged_params = {**params, **recorder.extra_params}
        try:
            record_operation(
                session_factory,
                agent_run_id=agent_run_id,
                op_name=op_name,
                params=merged_params,
                target_table=recorder.target_table or target_table,
                input_sha=recorder.input_sha,
                rows_affected=recorder.rows_affected,
                delta_version_before=recorder.delta_version_before,
                delta_version_after=recorder.delta_version_after,
                started_at=started_at,
                finished_at=finished_at,
                error_message=error_message,
            )
        except AuditUnavailableError:
            logger.exception(
                "operation_context: trail insert failed for run=%s op=%s "
                "while handling primitive exception",
                agent_run_id,
                op_name,
            )
        raise

    finished_at = datetime.datetime.now(datetime.UTC)
    merged_params = {**params, **recorder.extra_params}
    final_target = recorder.target_table or target_table
    op_id = record_operation(
        session_factory,
        agent_run_id=agent_run_id,
        op_name=op_name,
        params=merged_params,
        target_table=final_target,
        input_sha=recorder.input_sha,
        rows_affected=recorder.rows_affected,
        delta_version_before=recorder.delta_version_before,
        delta_version_after=recorder.delta_version_after,
        started_at=started_at,
        finished_at=finished_at,
        error_message=None,
    )
    _emit_lineage_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        op_name=op_name,
        target_table=final_target,
        params=merged_params,
        extra_params=recorder.extra_params,
    )


def _emit_lineage_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    op_name: str,
    target_table: str | None,
    params: dict[str, Any],
    extra_params: dict[str, Any],
) -> None:
    """Fire the soyuz OpenLineage event for a freshly-committed op row.

    Best-effort. A failure stamps a ``[lineage_emit_failed]`` marker
    onto the row's ``error_message`` field so the audit trail records
    that the side-effect was attempted but didn't reach soyuz; the
    underlying PQL write is never blocked.

    Args:
        session_factory: SQLAlchemy session factory used both to
            update the marker on failure and (transitively) by the
            soyuz client factory.
        op_id: Auto-assigned primary key of the just-committed
            ``agent_run_operations`` row.
        agent_run_id: PointlesSQL run UUID; used as the OpenLineage
            ``runId``.
        op_name: PQL primitive name.
        target_table: Output table FQN or ``None`` for read-only ops.
        params: Merged params dict (initial + recorder extras) used
            to derive ``referenced_tables`` for SQL ops.
        extra_params: Recorder extras alone — checked for
            ``source_table_fqn`` / ``source_volume_fqn`` declared by
            merge / write_table / autoload callers.
    """
    inputs: list[str] = []
    outputs: list[str] = []
    if target_table:
        outputs = [target_table]
    if op_name == "sql":
        refs = params.get("referenced_tables")
        if isinstance(refs, list):
            inputs = [str(r) for r in refs if isinstance(r, str)]
    else:
        src = extra_params.get("source_table_fqn")
        if isinstance(src, str) and src:
            inputs = [src]

    if not inputs and not outputs:
        return

    from pointlessql.services.soyuz_lineage import emit_event_sync

    failure = emit_event_sync(
        run_id=agent_run_id,
        op_name=op_name,
        inputs=inputs,
        outputs=outputs,
    )
    if failure is None:
        return

    marker = f"{_LINEAGE_FAILED_MARKER} {failure!r}"
    try:
        with session_factory() as session:
            row = session.get(AgentRunOperation, op_id)
            if row is None:
                return
            row.error_message = marker
            session.commit()
    except SQLAlchemyError:
        logger.exception(
            "operation_context: failed to stamp lineage_emit_failed marker on op_id=%s",
            op_id,
        )
