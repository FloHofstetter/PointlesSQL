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

from pointlessql.enums import OpName
from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import AuditUnavailableError, PointlessSQLError
from pointlessql.identifiers import OpId, RunId
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs.mlflow_detector import detect_mlflow_run_id

_LINEAGE_FAILED_MARKER = "[lineage_emit_failed]"

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


VALID_OP_NAMES = frozenset(
    {
        "autoload",
        "merge",
        "write_table",
        "sql",
        "aggregate",
        "rollback",
        "train_model",
        "branch_create",
        "branch_promote",
        "branch_discard",
        # dbt-bridge ops (Phase 36).  ``dbt_model`` covers run /
        # snapshot / seed (anything that materialises a relation);
        # ``dbt_test`` covers test executions.
        "dbt_model",
        "dbt_test",
        # Phase 39: pre-flight EXPLAIN call from an agent run.  Records
        # that the LLM looked at a query's plan + cost-gate verdict
        # before deciding whether to execute or rewrite.  No data
        # written; ``target_table`` and ``rows_affected`` stay NULL.
        "sql_explain",
    }
)


class RollbackError(PointlessSQLError):
    """Base class for ``pql.rollback`` failures.

    Subclasses encode the four refusal modes the rollback primitive
    surfaces: target-not-found, ambiguous (multi-op runs), invalid
    (creation ops), and stale (intervening writes).  Raising any
    subclass guarantees no Delta state has been mutated — the
    ``DeltaTable.restore(...)`` call is gated on all four checks
    passing first.

    Reparented from :class:`Exception` so the centralised
    :class:`PointlessSQLError` handler picks every refusal up
    automatically (no inline ``except`` translation at the route).
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.ROLLBACK_ERROR


class RollbackTargetNotFound(RollbackError):
    """No ``agent_run_operations`` row matches ``(run_id, target)``.

    Either the run never wrote to the named target, or the run id is
    unknown to the registry.  The caller should treat this as a
    user error (likely mistyped FQN or wrong run id).
    """

    status_code: int = 404
    error_code: ErrorCode = ErrorCode.ROLLBACK_TARGET_NOT_FOUND


class RollbackAmbiguous(RollbackError):
    """Multiple ops in one run touched the same target.

    Common for runs that ran ``pql.merge`` more than once on the
    same table.  The caller must re-issue with an explicit
    ``op_ordinal=N`` to disambiguate.  ``self.candidates`` carries
    the matching operation rows ordered by ``ordinal``; each row
    exposes the ``ordinal`` / ``delta_version_before`` /
    ``delta_version_after`` triple the caller needs to pick.

    Attributes:
        status_code: HTTP 409 — surfaced via the FastAPI handler.
        error_code: :data:`ErrorCode.ROLLBACK_AMBIGUOUS` for the
            problem-detail envelope.

    Args:
        candidates: The list of matching operation rows ordered
            by ``ordinal``.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.ROLLBACK_AMBIGUOUS

    def __init__(self, candidates: list[AgentRunOperation]) -> None:
        ordinals = [c.ordinal for c in candidates]
        super().__init__(
            f"rollback: {len(candidates)} ops match (ordinals={ordinals}); "
            f"pass op_ordinal=N to pick"
        )
        self.candidates = candidates

    def extension_members(self) -> dict[str, Any] | None:
        """Surface candidate ordinals as RFC 9457 extension members."""
        return {"candidate_ordinals": [c.ordinal for c in self.candidates]}


class RollbackInvalid(RollbackError):
    """Chosen op has ``delta_version_before is None``.

    The op created the table, so rolling it back would mean
    dropping the table — that is a different primitive
    (``pql.drop_table``) and is out of v1 scope.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.ROLLBACK_INVALID


class RollbackStale(RollbackError):
    """Current Delta version moved past the targeted op's version.

    Restoring would silently overwrite intervening writes by other
    runs.  The caller must re-issue with ``allow_force=True`` to
    confirm they accept that loss.  ``self.current_version`` /
    ``self.expected_version`` / ``self.intervening_op_count``
    carry the staleness-check result for the UI confirmation
    dialog.

    Attributes:
        status_code: HTTP 409 — surfaced via the FastAPI handler.
        error_code: :data:`ErrorCode.ROLLBACK_STALE` for the
            problem-detail envelope.

    Args:
        current_version: ``DeltaTable.version()`` at the moment
            of the staleness check.
        expected_version: The targeted op's
            ``delta_version_after``; equal to
            ``current_version`` for the non-stale path.
        intervening_op_count: Number of ``agent_run_operations``
            rows with the same ``target_table`` and a
            ``delta_version_after`` strictly greater than the
            targeted op's.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.ROLLBACK_STALE

    def __init__(
        self,
        *,
        current_version: int,
        expected_version: int,
        intervening_op_count: int,
    ) -> None:
        super().__init__(
            f"rollback stale: current_version={current_version} "
            f"expected={expected_version} "
            f"intervening_op_count={intervening_op_count}; "
            f"pass allow_force=True to overwrite intervening writes"
        )
        self.current_version = current_version
        self.expected_version = expected_version
        self.intervening_op_count = intervening_op_count

    def extension_members(self) -> dict[str, Any] | None:
        """Surface staleness-check fields as RFC 9457 extension members."""
        return {
            "current_version": self.current_version,
            "expected_version": self.expected_version,
            "intervening_op_count": self.intervening_op_count,
        }


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
        pending_lineage_edges:  hook — when a primitive
            knows the source-row → target-row mapping for a merge or
            write that carried ``_lineage_row_id`` it stashes
            ``{"source_table": str, "source_row_ids": list[str],
            "target_row_ids": list[str]}`` here.  The post-commit
            hook reads it (after ``op_id`` is known) and bulk-inserts
            into ``lineage_row_edges`` best-effort.
        pending_rejects:  hook — when a primitive ran
            with ``track_rejects=True`` and identified source rows
            that won't land in the target, it stashes
            ``{"source_table": str,
            "rejects": list[tuple[source_row_id, reason, detail]]}``
            here.  The post-commit hook bulk-inserts into
            ``lineage_row_rejects`` best-effort.
        pending_column_edges:  hook — every PQL
            primitive populates this with a list of
            :class:`~pointlessql.services.lineage_edges.ColumnEdgeSpec`
            entries describing the source-column → target-column
            mappings discovered at op time.  The post-commit hook
            bulk-inserts into ``lineage_column_map`` best-effort.
            ``None`` (the default) means the primitive had no
            mappings to record (e.g. read-only ops, or a write that
            ran without ``source_table_fqn``).
        pending_value_changes:  hook — when
            ``pql.merge(strategy="upsert", track_value_changes=True)``
            captured per-cell preimage/postimage pairs from the Delta
            CDF stream, it stashes the resulting list of
            :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
            entries here.  The post-commit hook bulk-inserts into
            ``lineage_value_changes`` best-effort.  ``None`` (the
            default) means the merge ran without opt-in or had no
            actual value differences.
        training_params_json:  hook — when ``pql.training_context()``
            wraps a training block with ``mlflow.autolog()`` enabled,
            it captures ``run.data.params`` + ``run.data.metrics`` at
            MLflow run-exit time and stashes the JSON-encoded blob
            here so :func:`record_operation` writes it onto
            ``agent_run_operations.training_params_json``.  ``None``
            for non-training ops.
        warnings: Non-fatal side-effect markers stamped by post-commit
            hooks (lineage emit, edge insert, reject, column, value-
            change failures).  Persisted into the row's
            ``warnings_json`` column so ``error_message`` stays clean.
    """

    input_sha: str | None = None
    rows_affected: int | None = None
    delta_version_before: int | None = None
    delta_version_after: int | None = None
    target_table: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)
    pending_lineage_edges: dict[str, Any] | None = None
    pending_rejects: dict[str, Any] | None = None
    pending_column_edges: list[Any] | None = None
    pending_value_changes: list[Any] | None = None
    # autolog snapshot {"params": {...}, "metrics": {...}}
    # populated by ``training_context`` at MLflow run-exit time.
    training_params_json: str | None = None
    # BUG-grand-08 — non-fatal side-effect markers stamped by
    # post-commit hooks (lineage emit / edge insert / reject /
    # column / value-change failures).  Persisted into the row's
    # ``warnings_json`` column so ``error_message`` stays clean.
    warnings: list[str] = field(default_factory=list)


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
                warnings_json=_serialise_warnings(recorder.warnings),
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
        warnings_json=_serialise_warnings(recorder.warnings),
    )
    _emit_lineage_after_commit(
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
    _record_row_edges_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        target_table=final_target,
        pending=recorder.pending_lineage_edges,
    )
    _record_rejects_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_rejects,
    )
    _record_column_edges_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_column_edges,
    )
    _record_value_changes_after_commit(
        session_factory,
        op_id=op_id,
        agent_run_id=agent_run_id,
        pending=recorder.pending_value_changes,
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
    pending_column_edges: list[Any] | None = None,
    pending_value_changes: list[Any] | None = None,
) -> None:
    """Fire the soyuz OpenLineage event for a freshly-committed op row.

    Best-effort. A failure stamps a ``[lineage_emit_failed]`` marker
    into the row's ``warnings_json`` blob so the audit trail records
    that the side-effect was attempted but didn't reach soyuz; the
    underlying PQL write is never blocked, and ``error_message``
    stays reserved for "the primitive itself raised" (BUG-grand-08).

     extends the body with two optional output facets when
    the recorder collected matching pending entries:

    * ``columnLineage`` (OpenLineage 1.x) — built from
      ``pending_column_edges`` (one
      :class:`pointlessql.services.lineage_edges.ColumnEdgeSpec`
      per entry).
    * ``valueChange`` (PointlesSQL extension) — built from
      ``pending_value_changes`` (one
      :class:`pointlessql.services.lineage_edges.ValueChangeSpec`
      per entry).  PointlesSQL emits **already-redacted** values so
      cleartext PII never leaves the install.

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
        pending_column_edges: Optional list of
            :class:`ColumnEdgeSpec` rows the merge / declarative
            primitive collected; populates the columnLineage facet.
        pending_value_changes: Optional list of
            :class:`ValueChangeSpec` rows the
            ``track_value_changes`` opt-in collected; populates the
            valueChange facet.
    """
    if op_name == OpName.ROLLBACK:
        return
    inputs: list[str] = []
    outputs: list[str] = []
    if target_table:
        outputs = [target_table]
    if op_name == OpName.SQL:
        refs = params.get("referenced_tables")
        if isinstance(refs, list):
            inputs = [str(r) for r in refs if isinstance(r, str)]
    else:
        src = extra_params.get("source_table_fqn")
        if isinstance(src, str) and src:
            inputs = [src]

    if not inputs and not outputs:
        return

    column_edges_payload: list[dict[str, Any]] = []
    if pending_column_edges:
        for spec in pending_column_edges:
            column_edges_payload.append(
                {
                    "source_table": getattr(spec, "source_table", None),
                    "source_column": getattr(spec, "source_column", None),
                    "target_column": getattr(spec, "target_column", None),
                    "transform_kind": getattr(spec, "transform_kind", None),
                }
            )

    value_changes_payload: list[dict[str, Any]] = []
    if pending_value_changes:
        for spec in pending_value_changes:
            value_changes_payload.append(
                {
                    "row_id": getattr(spec, "target_row_id", None),
                    "column": getattr(spec, "target_column", None),
                    "old_value": getattr(spec, "old_value", None),
                    "new_value": getattr(spec, "new_value", None),
                }
            )

    from pointlessql.services.soyuz_lineage import emit_event_sync

    failure = emit_event_sync(
        run_id=agent_run_id,
        op_name=op_name,
        inputs=inputs,
        outputs=outputs,
        column_edges=column_edges_payload or None,
        value_changes=value_changes_payload or None,
    )
    if failure is None:
        return

    _stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"{_LINEAGE_FAILED_MARKER} {failure!r}"
    )


def _record_row_edges_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    target_table: str | None,
    pending: dict[str, Any] | None,
) -> None:
    """Persist  per-row lineage edges in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        target_table: Output table FQN; required to record edges.
        pending: ``OperationRecorder.pending_lineage_edges`` payload
            populated by ``pql.merge`` / ``pql.write_table`` when the
            source carried a ``_lineage_row_id`` column and the
            caller declared ``source_table_fqn``.  ``None`` when the
            primitive had no lineage to record.
    """
    if not pending or not target_table:
        return
    source_table = pending.get("source_table")
    source_row_ids = pending.get("source_row_ids")
    target_row_ids = pending.get("target_row_ids")
    source_model_uri = pending.get("source_model_uri")
    if (
        not isinstance(source_table, str)
        or not isinstance(source_row_ids, list)
        or not isinstance(target_row_ids, list)
        or not source_row_ids
    ):
        return

    from pointlessql.services.lineage_edges import record_edges

    failure = record_edges(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        source_table=source_table,
        target_table=target_table,
        source_row_ids=[str(s) for s in source_row_ids],
        target_row_ids=[str(t) for t in target_row_ids],
        source_model_uri=source_model_uri if isinstance(source_model_uri, str) else None,
    )
    if failure is None:
        return
    _stamp_audit_marker(session_factory, op_id=op_id, marker=f"[lineage_edges_partial] {failure!r}")


def _record_rejects_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: dict[str, Any] | None,
) -> None:
    """Persist  reject markers in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_rejects`` payload —
            ``{"source_table": str, "rejects": list[tuple[str, str,
            str | None]]}`` where each tuple is
            ``(source_row_id, reason, detail)``.  ``None`` when the
            primitive did not run with ``track_rejects=True`` or had
            no rows to drop.
    """
    if not pending:
        return
    source_table = pending.get("source_table")
    rejects = pending.get("rejects")
    if not isinstance(source_table, str) or not isinstance(rejects, list) or not rejects:
        return

    from pointlessql.services.lineage_edges import record_rejects

    failure = record_rejects(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        source_table=source_table,
        rejects=rejects,
    )
    if failure is None:
        return
    _stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"[lineage_rejects_partial] {failure!r}"
    )


def _record_column_edges_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: list[Any] | None,
) -> None:
    """Persist  column-level lineage edges in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_column_edges`` payload —
            a list of
            :class:`~pointlessql.services.lineage_edges.ColumnEdgeSpec`
            entries.  ``None`` or empty when the primitive had no
            mappings to record.
    """
    if not pending:
        return

    from pointlessql.services.lineage_edges import record_column_edges

    failure = record_column_edges(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        edges=pending,
    )
    if failure is None:
        return
    _stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"[lineage_column_partial] {failure!r}"
    )


def _record_value_changes_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: list[Any] | None,
) -> None:
    """Persist  per-cell value changes in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_value_changes`` payload —
            a list of
            :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
            entries.  ``None`` or empty when the merge ran without
            opt-in or had no actual value differences.
    """
    if not pending:
        return

    from pointlessql.services.lineage_edges import record_value_changes
    from pointlessql.settings import Settings

    settings = Settings()
    failure = record_value_changes(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        changes=pending,
        pii_mode=settings.audit.pii_mode,
        pii_hash_secret=settings.audit.pii_hash_secret,
    )
    if failure is None:
        return
    _stamp_audit_marker(session_factory, op_id=op_id, marker=f"[lineage_value_partial] {failure!r}")


def _serialise_warnings(markers: list[str]) -> str | None:
    """Encode a marker list into the ``warnings_json`` blob shape.

    Returns ``None`` for an empty list so the column stays NULL when
    nothing was stamped; otherwise emits ``{"markers": [...]}`` so
    downstream consumers can extend the shape with new sub-keys
    without another schema change.
    """
    if not markers:
        return None
    return json.dumps({"markers": list(markers)}, sort_keys=False)


def _stamp_audit_marker(session_factory: sessionmaker[Session], *, op_id: int, marker: str) -> None:
    """Append a best-effort marker to ``agent_run_operations.warnings_json``.

    Used when a side-effect (lineage emit, edge insert, reject /
    column / value-change record) failed but the underlying op
    succeeded — the audit row should still record that the
    side-effect was attempted, but ``error_message`` must stay
    reserved for "the primitive itself raised" (BUG-grand-08).

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Operation row to update.
        marker: Bracketed-marker prefixed string to append.
    """
    try:
        with session_factory() as session:
            row = session.get(AgentRunOperation, op_id)
            if row is None:
                return
            existing_markers: list[str] = []
            if row.warnings_json:
                try:
                    parsed = json.loads(row.warnings_json)
                    if isinstance(parsed, dict):
                        raw = parsed.get("markers")
                        if isinstance(raw, list):
                            existing_markers = [str(m) for m in raw]
                except TypeError, ValueError:
                    # Corrupted blob — discard and start fresh; we
                    # never lose successful primitive output here, only
                    # the previous warning history.
                    logger.warning(
                        "operation_context: warnings_json on op_id=%s was unparseable, resetting",
                        op_id,
                    )
            existing_markers.append(marker)
            row.warnings_json = json.dumps({"markers": existing_markers}, sort_keys=False)
            session.commit()
    except SQLAlchemyError:
        logger.exception(
            "operation_context: failed to stamp marker on op_id=%s: %s",
            op_id,
            marker,
        )
