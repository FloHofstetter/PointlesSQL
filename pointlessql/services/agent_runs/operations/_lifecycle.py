"""Lifecycle path: insert + context-manager wrapper.

:func:`record_operation` is the single insert path for
``agent_run_operations`` rows.  :func:`operation_context` is the
context-manager wrapper every PQL primitive uses — it yields an
:class:`OperationRecorder` for the primitive to mutate, then on
exit either commits the row (success) or commits + re-raises
(failure).  Five sibling post-commit hooks fire after a successful
op to persist lineage / rejects / column / value-change side
effects best-effort.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.enums import OpName
from pointlessql.exceptions import AuditUnavailableError
from pointlessql.identifiers import OpId, RunId
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs.mlflow_detector import detect_mlflow_run_id
from pointlessql.services.agent_runs.operations._common import (
    VALID_OP_NAMES,
    OperationRecorder,
    serialise_warnings,
)
from pointlessql.services.agent_runs.operations._lineage import (
    emit_lineage_after_commit,
    record_column_edges_after_commit,
    record_row_edges_after_commit,
)
from pointlessql.services.agent_runs.operations._rejects import (
    record_rejects_after_commit,
)
from pointlessql.services.agent_runs.operations._value_changes import (
    record_value_changes_after_commit,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def record_operation(
    session_factory: sessionmaker[Session],
    *,
    agent_run_id: RunId,
    op_name: OpName,
    params: dict[str, Any],
    target_table: str | None,
    input_sha: str | None,
    rows_affected: int | None,
    delta_version_before: int | None,
    delta_version_after: int | None,
    started_at: datetime.datetime,
    finished_at: datetime.datetime | None,
    error_message: str | None,
    training_params_json: str | None = None,
    env_snapshot: str | None = None,
    warnings_json: str | None = None,
) -> OpId:
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
        training_params_json: JSON blob with
            ``params`` and ``metrics`` sub-keys captured from
            MLflow autolog.  ``None`` for non-training ops.
        env_snapshot: advisory hardware/library
            fingerprint blob.  When ``None``, the cached
            process-wide snapshot is stamped automatically.
        warnings_json: BUG-grand-08 — JSON blob with a ``markers``
            sub-key listing non-fatal side-effect failures
            stamped before commit.  Defaults to ``None``;
            post-commit hooks append further markers via
            :func:`_stamp_audit_marker`.

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

    #  cross-link: sniff MLflow's active_run() so audit rows
    # link to the matching MLflow run without an out-of-band lookup.
    # Side-effect-free; returns ``None`` for non-ML ops.
    mlflow_run_id = detect_mlflow_run_id()

    # stamp the cached env-fingerprint when the caller
    # didn't supply one.  Best-effort — `cached_env_snapshot()` returns
    # `None` if the import-time capture failed; we never raise.
    if env_snapshot is None:
        try:
            from pointlessql.services.agent_runs.env_snapshot import cached_env_snapshot

            env_snapshot = cached_env_snapshot()
        except Exception:  # noqa: BLE001 — env-snapshot is advisory
            # bare-broad-ok: env-snapshot is metadata-only; absence is acceptable
            env_snapshot = None

    try:
        with session_factory() as session:
            # Derive workspace_id from the parent run.
            # AgentRunOperation rows are scoped by the same workspace
            # as their owning AgentRun.  We fetch the parent's
            # workspace_id once and pass it through; the AuditUnavailableError
            # below covers the "no such parent" path.
            parent_row = session.scalar(
                select(AgentRun.id, AgentRun.workspace_id).where(AgentRun.id == agent_run_id)
            )
            run_exists = parent_row
            if run_exists is None:
                raise AuditUnavailableError(
                    f"agent_run_operations: agent_run_id {agent_run_id!r} is not registered"
                )
            parent_workspace_id = int(
                session.scalar(select(AgentRun.workspace_id).where(AgentRun.id == agent_run_id))
                or 1
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
                workspace_id=parent_workspace_id,
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
                mlflow_run_id=mlflow_run_id,
                training_params_json=training_params_json,
                env_snapshot=env_snapshot,
                warnings_json=warnings_json,
            )
            session.add(row)
            # backfill the parent agent_runs row's
            # mlflow_run_id on first detection.  Subsequent ops on the
            # same parent leave it untouched.
            if mlflow_run_id is not None:
                parent = session.get(AgentRun, agent_run_id)
                if parent is not None and parent.mlflow_run_id is None:
                    parent.mlflow_run_id = mlflow_run_id
            session.commit()
            session.refresh(row)
            return OpId(row.id)
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
    agent_run_id: RunId | None,
    op_name: OpName,
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
                training_params_json=recorder.training_params_json,
                warnings_json=serialise_warnings(recorder.warnings),
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
        training_params_json=recorder.training_params_json,
        warnings_json=serialise_warnings(recorder.warnings),
    )
    emit_lineage_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        op_name=op_name,
        target_table=final_target,
        params=merged_params,
        extra_params=recorder.extra_params,
        pending_column_edges=recorder.pending_column_edges,
        pending_value_changes=recorder.pending_value_changes,
    )
    record_row_edges_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        target_table=final_target,
        pending=recorder.pending_lineage_edges,
    )
    record_rejects_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_rejects,
    )
    record_column_edges_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_column_edges,
    )
    record_value_changes_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_value_changes,
    )
