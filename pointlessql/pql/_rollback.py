"""``pql.rollback()`` — first-class undo for a prior agent run.

The rollback primitive closes the audit→action loop opened by
Phases 13–15.7.  It looks up an ``agent_run_operations`` row by
``(run_id, target_table)``, captures the recorded
``delta_version_before``, and atomically restores the Delta table
to that version via :meth:`deltalake.DeltaTable.restore`.

The primitive itself is one ``agent_run_operations`` row — a
rollback IS an operation.  Its ``params_json`` records the
rolled-back run + op id, the target version that was restored,
and whether ``allow_force`` was passed to suppress staleness
checks.  The recorder skips lineage / row-edge / column-edge /
value-change emission for ``op_name='rollback'`` because the
restored rows are pre-existing — there is no source-to-target
mapping to carry forward.

Order of operations is load-bearing.  All four refusal modes
(target-not-found, ambiguous, invalid, stale) are evaluated
*before* :meth:`DeltaTable.restore` is called.  The recorder is
opened around the entire body so the audit row records the
attempted rollback even when one of the gates raises — but the
Delta state is only mutated on the happy path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from deltalake import CommitProperties, DeltaTable
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset
from sqlalchemy import select

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.models import AgentRunOperation
from pointlessql.services.agent_runs import operation_context
from pointlessql.services.agent_runs.operations import (
    RollbackAmbiguous,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of a successful ``pql.rollback`` call.

    Attributes:
        version_before: Delta version of the target *immediately
            before* the restore commit (i.e. the version that
            staleness was checked against).
        version_after: Delta version of the target *immediately
            after* the restore commit.  Always greater than
            ``version_before`` because restore writes a new
            commit; it does not rewind.
        target_version_restored: The historical version whose
            file set was re-added (the targeted op's
            ``delta_version_before``).
        restored_file_count: Number of parquet files re-added by
            the restore commit, or ``None`` when the deltalake
            metrics dict didn't expose the key.
    """

    version_before: int
    version_after: int
    target_version_restored: int
    restored_file_count: int | None


def rollback_table(
    *,
    client: Client,
    target: str,
    before_run: str,
    unreachable_msg: str,
    op_ordinal: int | None = None,
    allow_force: bool = False,
    agent_run_id: str | None = None,
) -> RollbackResult:
    """Rollback *target* to the version captured before *before_run* wrote it.

    Resolves the targeted operation by querying
    ``agent_run_operations`` for rows matching ``(before_run,
    target)``.  When the run wrote the same table multiple times,
    *op_ordinal* must disambiguate.  When the table moved past the
    targeted op's ``delta_version_after``, *allow_force* must be
    set to confirm intervening writes will be overwritten.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        target: UC ``"catalog.schema.table"`` string.  Must exist
            in soyuz-catalog with a ``storage_location``.
        before_run: ``agent_runs.id`` of the run whose write to
            *target* is being undone.
        unreachable_msg: Pre-rendered "cannot reach catalog"
            message — same hop the read/write helpers take.
        op_ordinal: When the run touched *target* more than once,
            the explicit ``ordinal`` of the op to rollback.
            ``None`` is valid only when exactly one op matches.
        allow_force: When ``True``, bypass the staleness check.
            Defaults to ``False`` so a casual click cannot
            silently overwrite intervening writes.
        agent_run_id: When set, the rollback is recorded under
            this run id (a fresh "rollback run" the caller
            spawned).  ``None`` skips audit emission — used only
            by the test harness; the public ``pql.rollback``
            wrapper always passes a run id.

    Returns:
        A :class:`RollbackResult` carrying the version delta and
        the number of files restored.

    Raises:
        RollbackTargetNotFound: No ``agent_run_operations`` row
            matches the (run, target) pair.
        RollbackAmbiguous: Multiple rows match and *op_ordinal*
            was not supplied (or did not pick a row).
        RollbackInvalid: The chosen op's ``delta_version_before``
            is ``None`` (it created the table; rollback would
            mean dropping it — out of v1 scope).
        RollbackStale: ``DeltaTable.version()`` no longer matches
            the chosen op's ``delta_version_after`` and
            *allow_force* is ``False``.
        CatalogNotFoundError: *target* is unknown to
            soyuz-catalog or has no ``storage_location``.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        AuditUnavailableError: When *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC502,DOC503 — Catalog* / Rollback* / AuditUnavailableError propagate
    target_location = _resolve_target_location(client, target, unreachable_msg)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=agent_run_id,
        op_name="rollback",
        params={
            "target": target,
            "rolled_back_run": before_run,
            "op_ordinal": op_ordinal,
            "allow_force": allow_force,
        },
        target_table=target,
    ) as recorder:
        if factory is None:
            chosen = _resolve_target_op_no_session(
                before_run=before_run, target=target, op_ordinal=op_ordinal
            )
        else:
            chosen = _resolve_target_op(
                factory,
                before_run=before_run,
                target=target,
                op_ordinal=op_ordinal,
            )

        if chosen.delta_version_before is None:
            raise RollbackInvalid(
                f"rollback: op {chosen.id} on {target!r} created the table "
                "(delta_version_before is None); use pql.drop_table to undo"
            )

        dt = DeltaTable(target_location)
        current_version = int(dt.version())
        recorder.delta_version_before = current_version

        if chosen.delta_version_after is not None and current_version != chosen.delta_version_after:
            intervening = (
                _count_intervening_ops(
                    factory,
                    target=target,
                    after_version=chosen.delta_version_after,
                )
                if factory is not None
                else 0
            )
            if not allow_force:
                raise RollbackStale(
                    current_version=current_version,
                    expected_version=chosen.delta_version_after,
                    intervening_op_count=intervening,
                )

        target_version = int(chosen.delta_version_before)
        metrics = dt.restore(
            target_version,
            commit_properties=CommitProperties(
                custom_metadata={
                    "pointlessql.rollback_of_run": before_run,
                    "pointlessql.rollback_of_op_id": str(chosen.id),
                }
            ),
        )
        dt.update_incremental()

        version_after = int(dt.version())
        recorder.delta_version_after = version_after
        restored_files = _coerce_int(metrics.get("num_restored_file"))
        recorder.rows_affected = restored_files
        recorder.extra_params.update(
            {
                "rolled_back_op_id": chosen.id,
                "target_version_restored": target_version,
                "metrics": metrics,
                "allow_force": allow_force,
            }
        )

        return RollbackResult(
            version_before=current_version,
            version_after=version_after,
            target_version_restored=target_version,
            restored_file_count=restored_files,
        )


def _resolve_target_op(
    factory: sessionmaker[Session],
    *,
    before_run: str,
    target: str,
    op_ordinal: int | None,
) -> AgentRunOperation:
    """Look up the ``agent_run_operations`` row to rollback.

    Args:
        factory: SQLAlchemy session factory.
        before_run: ``agent_runs.id`` to filter on.
        target: ``target_table`` to filter on.
        op_ordinal: Optional explicit ordinal pick.  When ``None``,
            the call is ambiguous if more than one row matches.

    Returns:
        The single matching :class:`AgentRunOperation` row.

    Raises:
        RollbackTargetNotFound: Empty result set.
        RollbackAmbiguous: More than one row matched and
            *op_ordinal* did not narrow to a unique pick.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == before_run)
                .where(AgentRunOperation.target_table == target)
                .order_by(AgentRunOperation.ordinal)
            )
        )
        for row in rows:
            session.expunge(row)
    if not rows:
        raise RollbackTargetNotFound(
            f"rollback: no agent_run_operations row found for run={before_run!r} target={target!r}"
        )
    if op_ordinal is not None:
        picked = [r for r in rows if r.ordinal == op_ordinal]
        if not picked:
            raise RollbackTargetNotFound(
                f"rollback: op_ordinal={op_ordinal} did not match any of the "
                f"{len(rows)} rows for run={before_run!r} target={target!r}"
            )
        return picked[0]
    if len(rows) > 1:
        raise RollbackAmbiguous(rows)
    return rows[0]


def _resolve_target_op_no_session(
    *,
    before_run: str,
    target: str,
    op_ordinal: int | None,
) -> AgentRunOperation:
    """No-session resolver path used when audit is disabled.

    The interactive ``pql.rollback`` path always emits an audit
    row, so this branch only fires from harness code that opts out
    by passing ``agent_run_id=None``.  We still need to surface a
    meaningful error rather than dereferencing a ``None`` factory.

    Args:
        before_run: As :func:`_resolve_target_op`.
        target: As :func:`_resolve_target_op`.
        op_ordinal: As :func:`_resolve_target_op`.

    Returns:
        Never — always raises.

    Raises:
        RollbackTargetNotFound: Always.  Audit-disabled rollback
            cannot resolve the target op without a session.
    """
    del op_ordinal  # documented as accepted but unused on this path
    raise RollbackTargetNotFound(
        f"rollback: cannot resolve op for run={before_run!r} target={target!r} "
        "without a session factory (pass agent_run_id to enable lookup)"
    )


def _count_intervening_ops(
    factory: sessionmaker[Session] | None,
    *,
    target: str,
    after_version: int,
) -> int:
    """Count ``agent_run_operations`` rows that wrote *target* after the targeted op.

    The number of intervening ops drives the staleness-warning UI
    (``"will overwrite N intervening write(s)"``).
    A best-effort count: a DB error returns ``0`` rather than
    raising into the rollback path.

    Args:
        factory: SQLAlchemy session factory, or ``None`` (caller
            chose audit-disabled mode).
        target: ``target_table`` to filter on.
        after_version: ``delta_version_after`` of the targeted op;
            rows with a strictly greater value are intervening.

    Returns:
        The intervening-op count, or ``0`` when the count couldn't
        be computed.
    """
    if factory is None:
        return 0
    try:
        with factory() as session:
            count = (
                session.query(AgentRunOperation)
                .filter(AgentRunOperation.target_table == target)
                .filter(AgentRunOperation.delta_version_after > after_version)
                .count()
            )
            return int(count)
    except Exception:  # noqa: BLE001 — best-effort count for the UI hint
        logger.exception("rollback: intervening-op count failed for target=%s", target)
        return 0


def _resolve_target_location(client: Client, full_name: str, unreachable_msg: str) -> str:
    """Look up *full_name* in soyuz-catalog and return its storage_location.

    Mirrors :func:`pointlessql.pql._merge._resolve_target_location`
    so the rollback primitive resolves targets exactly the same
    way as merge / write.

    Args:
        client: Configured catalog client.
        full_name: UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The Delta table's storage location URI.

    Raises:
        CatalogNotFoundError: Target is unknown or has no location.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(f"rollback target {full_name!r} not found in soyuz-catalog")
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(f"rollback target {full_name!r} has no storage_location")
    return location


def _coerce_int(value: Any) -> int | None:
    """Parse an int out of the deltalake restore-metrics dict.

    The deltalake-python 1.5.0 ``.pyi`` stub does not document the
    keys returned by ``restore``; observed runs return integer
    values for ``num_restored_file`` / ``num_removed_file`` but
    the dict shape is not strongly typed.  Coerce defensively so a
    surprise key shape (string, missing) doesn't break the audit
    row.

    Args:
        value: Raw value pulled from the metrics dict.

    Returns:
        The integer, or ``None`` when the value is missing or not
        coercible.
    """
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None
