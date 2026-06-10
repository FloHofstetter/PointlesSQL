"""Replay dispatcher — re-invoke a source run's operations on a branch.

Backs :func:`pointlessql.pql.memory.replay`.  The dispatcher creates
a new :class:`AgentRun`, walks the source run's recorded operations
in ordinal order, and routes each one to one of three outcomes:

* **replayable** (``SQL``, ``SQL_EXPLAIN``, ``AUTOLOAD``) — the op's
  params carry everything needed to re-record the action against
  the branch schema.  The dispatcher rewrites schema references in
  the params (``catalog.parent_schema.table`` →
  ``catalog.branch_schema.table``) and records a new operation on
  the replay run with ``_replay_of: <source_op_id>`` stamped into
  the params.
* **data_unavailable** (``MERGE``, ``WRITE_TABLE``, ``AGGREGATE``) —
  the original primitive took an in-memory DataFrame that no
  longer exists; the dispatcher records the skip with reason
  ``"data_unavailable"`` so the audit trail makes the gap
  explicit instead of pretending the replay was complete.
* **unsafe** (everything else — branch ops, dbt nodes,
  ``train_model``, DDL/DML mutations, ``rollback``) — semantically
  dangerous to blind-replay.  When ``policy=STRICT`` the
  dispatcher raises; otherwise the skip is recorded with reason
  ``"unsafe_op"``.

**Scope note**: ``replayable`` outcomes currently record *intent*
rather than executing the primitive.  Real execution (rebuilding a
DuckDB approved-tables map for the branch, re-running SQL against
branch storage) is deferred — it shares plumbing with the NL→SQL
chat panel.  The dispatcher's audit + UI surface is fully
functional today; the executed-vs-recorded distinction is called
out in the replay-run's operation rows so the UI can render the
disclaimer.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.exceptions import ValidationError
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.pql import memory as memory_facade
from pointlessql.services.agent_runs.memory._replay_policy import (
    ReplayPolicy,
    ReplayResult,
    ReplaySkip,
)
from pointlessql.types import OpId, OpName, RunId

if TYPE_CHECKING:
    from soyuz_catalog_client import Client
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.pql.engine import Engine


REPLAYABLE_OPS: frozenset[str] = frozenset(
    {
        OpName.SQL.value,
        OpName.SQL_EXPLAIN.value,
        OpName.AUTOLOAD.value,
        OpName.VECTOR_SEARCH.value,
    }
)
DATA_UNAVAILABLE_OPS: frozenset[str] = frozenset(
    {
        OpName.MERGE.value,
        OpName.WRITE_TABLE.value,
        OpName.AGGREGATE.value,
        # a fact points at a *specific*
        # revision UUID + workspace; replaying onto a branch would
        # either duplicate the pin (same revision, two workspaces)
        # or silently re-point at a different revision.  Neither is
        # the right semantic, so the dispatcher records the skip and
        # the audit trail makes the gap explicit.
        OpName.PIN_FACT.value,
    }
)
UNSAFE_OPS: frozenset[str] = frozenset(
    {
        OpName.BRANCH_CREATE.value,
        OpName.BRANCH_PROMOTE.value,
        OpName.BRANCH_DISCARD.value,
        OpName.DBT_MODEL.value,
        OpName.DBT_TEST.value,
        OpName.TRAIN_MODEL.value,
        OpName.UPDATE.value,
        OpName.DELETE.value,
        OpName.ROLLBACK.value,
        OpName.DROP_TABLE.value,
        OpName.CREATE_SCHEMA.value,
        OpName.DROP_SCHEMA.value,
        OpName.ALTER_TABLE.value,
        OpName.VECTOR_INDEX.value,
        OpName.CANVAS_MATERIALIZE.value,
        OpName.CANVAS_PIN.value,
        OpName.CANVAS_UNPIN.value,
    }
)


class ReplayUnsafeOpError(ValidationError):
    """Raised by the dispatcher under ``policy=STRICT`` for an unsafe op."""


def _split_branch_fqn(branch_schema_fqn: str) -> tuple[str, str]:
    """Decompose a two-part branch FQN into catalog + schema parts.

    Args:
        branch_schema_fqn: ``catalog.branch_schema``.

    Returns:
        ``(catalog, branch_schema)``.

    Raises:
        ValidationError: When the FQN does not have two
            dot-separated parts.
    """
    parts = branch_schema_fqn.split(".")
    if len(parts) != 2:
        raise ValidationError(
            f"replay: branch_schema_fqn must be two-part, got {branch_schema_fqn!r}"
        )
    return parts[0], parts[1]


def _rewrite_target_table(
    target_table: str | None,
    branch_catalog: str,
    branch_schema: str,
) -> str | None:
    """Rewrite a three-part target FQN's schema component to the branch.

    Args:
        target_table: ``catalog.schema.table`` or ``None``.
        branch_catalog: Branch catalog name.
        branch_schema: Branch schema name.

    Returns:
        ``catalog.branch_schema.table`` or ``None``.
    """
    if target_table is None:
        return None
    parts = target_table.split(".")
    if len(parts) != 3:
        # Best-effort — leave as-is rather than failing the whole replay.
        return target_table
    return f"{branch_catalog}.{branch_schema}.{parts[2]}"


def _rewrite_schema_refs_in_query(
    query: str,
    source_schema_fqn: str,
    branch_schema_fqn: str,
) -> str:
    """Rewrite source-schema references in a SQL query to the branch schema.

    Strategy: literal substitution of the two-part schema prefix on
    word-boundary matches.  Robust enough for the dot-delimited
    three-part identifiers PointlesSQL emits; insufficient for
    quoted-identifier corner cases (``"weird name"."table"``).
    Trades full completeness for a 6-line implementation;
    full sqlglot-AST rewriting is a follow-up.

    Args:
        query: Original SQL text.
        source_schema_fqn: ``catalog.parent_schema``.
        branch_schema_fqn: ``catalog.branch_schema``.

    Returns:
        Query with all ``parent_schema`` references swapped to
        ``branch_schema``.  Catalog prefix is preserved.
    """
    src_pattern = re.compile(rf"\b{re.escape(source_schema_fqn)}\b")
    return src_pattern.sub(branch_schema_fqn, query)


def _create_replay_run(
    session_factory: sessionmaker[Session],
    *,
    source: AgentRun,
    branch_schema_fqn: str,
    agent_id_override: str | None,
) -> RunId:
    """Insert a new :class:`AgentRun` row for the replay invocation.

    The replay run carries the same ``agent_id`` and ``principal``
    as the source so the UI's agent-memory page picks it up as
    another entry in the timeline.  The ``notebook_path`` is set
    to a sentinel string so a reviewer can distinguish replay runs
    from original runs at-a-glance in the runs list.

    Args:
        session_factory: SQLAlchemy session factory.
        source: Source :class:`AgentRun` being replayed.
        branch_schema_fqn: Branch the replay writes onto.
        agent_id_override: Optional override for ``agent_id``;
            defaults to ``source.agent_id``.

    Returns:
        The newly-assigned :class:`RunId`.
    """
    new_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        session.add(
            AgentRun(
                id=new_id,
                workspace_id=source.workspace_id,
                principal=source.principal,
                agent_id=agent_id_override or source.agent_id,
                notebook_path=f"<replay of {source.id}>",
                status="running",
                started_at=now,
                tables_touched=json.dumps([branch_schema_fqn]),
            )
        )
        session.commit()
    return RunId(new_id)


def _finalise_replay_run(
    session_factory: sessionmaker[Session],
    *,
    run_id: RunId,
    success: bool,
) -> None:
    """Stamp the replay run as finished with the appropriate status.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: Replay run UUID.
        success: ``True`` → ``status='succeeded'``;
            ``False`` → ``status='failed'``.
    """
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.get(AgentRun, str(run_id))
        if row is None:
            return
        row.status = "succeeded" if success else "failed"
        row.finished_at = now
        session.commit()


def _load_source_run(
    session_factory: sessionmaker[Session],
    source_run_id: RunId,
) -> AgentRun:
    """Fetch the source run row and validate it has operations.

    Args:
        session_factory: SQLAlchemy session factory.
        source_run_id: Source run UUID.

    Returns:
        The :class:`AgentRun` row.

    Raises:
        ValidationError: When the run is unknown or has zero
            recorded operations.
    """
    with session_factory() as session:
        run = session.get(AgentRun, str(source_run_id))
        if run is None:
            raise ValidationError(f"replay: source run {source_run_id!r} is not registered")
        count = session.scalar(
            select(AgentRunOperation.id)
            .where(AgentRunOperation.agent_run_id == str(source_run_id))
            .limit(1)
        )
        if count is None:
            raise ValidationError(
                f"replay: source run {source_run_id!r} has zero operations to replay"
            )
        # Detach so the row is usable after the session closes.
        session.expunge(run)
    return run


def _load_source_operations(
    session_factory: sessionmaker[Session],
    source_run_id: RunId,
) -> list[AgentRunOperation]:
    """Load the source run's operations ordered by ordinal."""
    with session_factory() as session:
        ops = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == str(source_run_id))
                .order_by(AgentRunOperation.ordinal)
            ).all()
        )
        for op in ops:
            session.expunge(op)
    return ops


def _derive_source_schema(
    operations: list[AgentRunOperation],
) -> str | None:
    """Pick the parent schema from the first op that carries a target."""
    for op in operations:
        if op.target_table:
            parts = op.target_table.split(".")
            if len(parts) == 3:
                return f"{parts[0]}.{parts[1]}"
    return None


def _replay_one_op(
    op: AgentRunOperation,
    *,
    session_factory: sessionmaker[Session],
    new_run_id: RunId,
    branch_catalog: str,
    branch_schema: str,
    branch_schema_fqn: str,
    source_schema_fqn: str | None,
) -> None:
    """Re-record one source op against the replay run with rewritten targets.

    the audit trail captures the would-have-been call so the UI's
    operation-tape on the replay run shows the trace.  See the
    module docstring for the broader scope note.

    Args:
        op: Source operation row.
        session_factory: SQLAlchemy session factory.
        new_run_id: Replay run UUID.
        branch_catalog: Branch catalog (for ``target_table`` rewrites).
        branch_schema: Branch schema (for ``target_table`` rewrites).
        branch_schema_fqn: Two-part branch FQN.
        source_schema_fqn: Parent schema; used to rewrite SQL text
            references.  ``None`` skips SQL rewriting.

    Raises:
        ValidationError: When the op's params_json is malformed.
    """
    try:
        params: dict[str, Any] = json.loads(op.params_json) if op.params_json else {}
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"replay: op {op.id} has malformed params_json") from exc

    rewritten_params: dict[str, Any] = dict(params)
    if op.op_name in {OpName.SQL.value, OpName.SQL_EXPLAIN.value}:
        query = params.get("query")
        if isinstance(query, str) and source_schema_fqn is not None:
            rewritten_params["query"] = _rewrite_schema_refs_in_query(
                query, source_schema_fqn, branch_schema_fqn
            )
            rewritten_params["_original_query"] = query
    rewritten_params["_replay_of"] = op.id
    rewritten_params["_replay_recorded_only"] = True

    new_target = _rewrite_target_table(op.target_table, branch_catalog, branch_schema)

    memory_facade.record(
        session_factory=session_factory,
        agent_run_id=new_run_id,
        op_name=OpName(op.op_name),
        params=rewritten_params,
        target_table=new_target,
    )


def replay_run_on_branch(
    *,
    client: Client,  # noqa: ARG001 — accepted for parity, used by real-execution follow-up
    engine: Engine,  # noqa: ARG001 — same
    session_factory: sessionmaker[Session],
    branch_schema_fqn: str,
    source_run_id: RunId,
    agent_id: str | None = None,
    policy: ReplayPolicy = ReplayPolicy.SKIP_UNSAFE,
    unreachable_msg: str,  # noqa: ARG001 — used by real-execution follow-up
) -> ReplayResult:
    """Replay a source run's operations onto a branch schema.

    Propagates :class:`ValidationError` from the source-run
    loading helpers when the source run is unknown or has no
    operations to replay.

    Args:
        client: Configured soyuz-catalog client.  Currently unused
            but kept in the signature so the follow-up real-
            execution implementation doesn't break callers.
        engine: Engine the future real-execution path will use.
        session_factory: SQLAlchemy session factory.
        branch_schema_fqn: ``catalog.branch_schema`` the replay
            writes against.
        source_run_id: Source run UUID.
        agent_id: Optional override for ``agent_id`` on the new
            replay run; defaults to the source run's ``agent_id``.
        policy: Replay policy — see :class:`ReplayPolicy`.
        unreachable_msg: Pre-rendered catalog-error string.

    Returns:
        :class:`ReplayResult` with the new run id, the count of
        replayable ops that were re-recorded, and a tuple of
        :class:`ReplaySkip` entries describing every skipped op.

    Raises:
        ReplayUnsafeOpError: When ``policy=STRICT`` and an unsafe
            op is encountered.
    """
    branch_catalog, branch_schema = _split_branch_fqn(branch_schema_fqn)
    source = _load_source_run(session_factory, source_run_id)
    operations = _load_source_operations(session_factory, source_run_id)
    source_schema_fqn = _derive_source_schema(operations)
    new_run_id = _create_replay_run(
        session_factory,
        source=source,
        branch_schema_fqn=branch_schema_fqn,
        agent_id_override=agent_id,
    )

    started_at = datetime.datetime.now(datetime.UTC)
    skipped: list[ReplaySkip] = []
    replayed = 0
    success = True

    try:
        for op in operations:
            if op.op_name in UNSAFE_OPS:
                if policy is ReplayPolicy.STRICT:
                    raise ReplayUnsafeOpError(
                        f"replay: op {op.id} ({op.op_name}) is classified as unsafe; "
                        f"policy=STRICT refuses to skip"
                    )
                skipped.append(
                    ReplaySkip(
                        op_id=OpId(op.id),
                        op_name=OpName(op.op_name),
                        reason="unsafe_op",
                    )
                )
                continue
            if op.op_name in DATA_UNAVAILABLE_OPS:
                skipped.append(
                    ReplaySkip(
                        op_id=OpId(op.id),
                        op_name=OpName(op.op_name),
                        reason="data_unavailable",
                    )
                )
                continue
            if op.op_name in REPLAYABLE_OPS:
                try:
                    _replay_one_op(
                        op,
                        session_factory=session_factory,
                        new_run_id=new_run_id,
                        branch_catalog=branch_catalog,
                        branch_schema=branch_schema,
                        branch_schema_fqn=branch_schema_fqn,
                        source_schema_fqn=source_schema_fqn,
                    )
                    replayed += 1
                except ValidationError as exc:
                    skipped.append(
                        ReplaySkip(
                            op_id=OpId(op.id),
                            op_name=OpName(op.op_name),
                            reason=f"dispatch_failed: {exc}",
                        )
                    )
                continue
            skipped.append(
                ReplaySkip(
                    op_id=OpId(op.id),
                    op_name=OpName(op.op_name),
                    reason="unknown_op_name",
                )
            )
    except ReplayUnsafeOpError:
        success = False
        raise
    finally:
        _finalise_replay_run(session_factory, run_id=new_run_id, success=success)

    finished_at = datetime.datetime.now(datetime.UTC)
    return ReplayResult(
        replay_run_id=new_run_id,
        ops_replayed=replayed,
        ops_skipped=tuple(skipped),
        started_at=started_at,
        finished_at=finished_at,
    )
