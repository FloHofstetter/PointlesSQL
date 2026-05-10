"""Value-level lineage capture + lookup.

Owns the ``LineageValueChange`` write path with the PII-redaction hook
plus the per-row value-changes lookup used by the row-trace UI.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models import LineageValueChange
from pointlessql.services.lineage._types import (
    MAX_VALUE_CHANGES_PER_OP,
    ValueChangeCapExceeded,
    ValueChangeSpec,
    logger,
    workspace_id_for_op,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def record_value_changes(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    changes: Sequence[ValueChangeSpec],
    pii_mode: str = "store_clear",
    pii_hash_secret: str | None = None,
) -> Exception | None:
    """Bulk-insert one row per :class:`ValueChangeSpec` into ``lineage_value_changes``.

    value-level analog of :func:`record_column_edges`.
    Same best-effort contract: the function returns the exception
    rather than raising, so a Delta merge that already committed never
    rolls back.  The audit row gets a ``[lineage_value_partial]``
    marker stamped by the caller.

    The 100k-row cap (:data:`MAX_VALUE_CHANGES_PER_OP`) gates
    pathological full-table upserts where most rows changed across
    most columns.  When breached the function inserts no rows and
    returns a :class:`ValueChangeCapExceeded` sentinel.

     adds the PII redaction hook: when ``pii_mode`` is
    ``hash_only`` or ``redact_with_audit_log``, every column whose
    name matches
    :data:`pointlessql.services.pii_redactor.PII_NAME_PATTERN` gets
    its ``old_value`` / ``new_value`` rewritten before insert.
    ``hash_only`` keeps equality joinable across runs; the
    ``redact_with_audit_log`` mode also appends a single
    ``audit_log`` row noting the redaction count.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: PointlesSQL ``agent_run_id`` driving the merge.
        op_id: ``agent_run_operations.id`` of the merge.
        changes: Value-change specs to persist.  Empty input is a
            no-op.
        pii_mode: One of ``store_clear`` (default — no rewrite),
            ``hash_only``, ``redact_with_audit_log``.  Resolves
            from :attr:`pointlessql.config.AuditSettings.pii_mode`
            in production callers.
        pii_hash_secret: Pre-shared secret for ``hash_only`` mode.
            ``None`` triggers a lazy auto-generation via
            :func:`pointlessql.services.pii_redactor.get_or_create_pii_hash_secret`.

    Returns:
        ``None`` on success or empty input.
        :class:`ValueChangeCapExceeded` when the cap was breached
        (zero rows written).  The underlying ``Exception`` when the
        bulk insert failed.
    """
    if not changes:
        return None

    if len(changes) > MAX_VALUE_CHANGES_PER_OP:
        msg = (
            f"value-change count {len(changes)} exceeds per-op cap "
            f"{MAX_VALUE_CHANGES_PER_OP}; skipping insert"
        )
        logger.info(
            "lineage_value_changes cap exceeded for run=%s op=%s: %s",
            run_id,
            op_id,
            msg,
        )
        return ValueChangeCapExceeded(msg)

    redacted_count = 0
    if pii_mode != "store_clear":
        from pointlessql.services.pii_redactor import (
            get_or_create_pii_hash_secret,
            hash_value,
            is_pii_by_name,
            redact_value,
        )

        secret: str | None = pii_hash_secret
        if pii_mode == "hash_only" and not secret:
            try:
                secret = get_or_create_pii_hash_secret(session_factory)
            except Exception:  # noqa: BLE001 — fall back to redact
                logger.exception(
                    "pii_redactor: secret generation failed (run=%s op=%s); "
                    "falling back to redact_with_audit_log mode for this op",
                    run_id,
                    op_id,
                )
                pii_mode = "redact_with_audit_log"

        new_changes: list[ValueChangeSpec] = []
        from dataclasses import replace as _dc_replace

        for change in changes:
            if not is_pii_by_name(change.target_column):
                new_changes.append(change)
                continue
            if pii_mode == "hash_only":
                new_changes.append(
                    _dc_replace(
                        change,
                        old_value=hash_value(change.old_value, secret=secret or ""),
                        new_value=hash_value(change.new_value, secret=secret or ""),
                    )
                )
            else:  # redact_with_audit_log
                new_changes.append(
                    _dc_replace(
                        change,
                        old_value=redact_value(change.old_value),
                        new_value=redact_value(change.new_value),
                    )
                )
            redacted_count += 1
        changes = new_changes

    now = datetime.datetime.now(datetime.UTC)
    workspace_id = workspace_id_for_op(session_factory, op_id)
    rows = [
        {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "op_id": op_id,
            "target_table": change.target_table,
            "target_row_id": change.target_row_id,
            "target_column": change.target_column,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "created_at": now,
        }
        for change in changes
    ]

    try:
        with session_factory() as session:
            session.execute(insert(LineageValueChange), rows)
            session.commit()
    except SQLAlchemyError as exc:
        logger.info(
            "lineage_value_changes insert failed for run=%s op=%s n=%s: %s",
            run_id,
            op_id,
            len(rows),
            exc,
        )
        return exc

    if pii_mode == "redact_with_audit_log" and redacted_count > 0:
        from pointlessql.services.audit import log_action

        try:
            log_action(
                session_factory,
                0,
                "system:pii_redactor",
                "pii_redact",
                f"agent_run_operations:{op_id}",
                {"redacted_count": redacted_count, "mode": pii_mode},
                actor_role="system",
            )
        except Exception:  # noqa: BLE001 — audit-log failure must not break write
            logger.exception(
                "pii_redactor: audit_log append failed for run=%s op=%s",
                run_id,
                op_id,
            )

    return None


def count_value_changes_for_op(
    session_factory: sessionmaker[Session], op_ids: Iterable[int]
) -> dict[int, int]:
    """Return ``{op_id: value_change_count}`` for the given ops.

    Used by the run-detail Operations tab to surface a "value changes:
    N" counter alongside the existing row-edge / column-edge counters.

    Args:
        session_factory: SQLAlchemy session factory.
        op_ids: Operation IDs to count value changes for.

    Returns:
        Mapping with one entry per op-id that produced at least one
        value change.
    """
    op_id_list = [int(o) for o in op_ids]
    if not op_id_list:
        return {}
    from sqlalchemy import func

    with session_factory() as session:
        stmt = (
            select(LineageValueChange.op_id, func.count(LineageValueChange.id))
            .where(LineageValueChange.op_id.in_(op_id_list))
            .group_by(LineageValueChange.op_id)
        )
        result: dict[int, int] = {}
        for op_id, count in session.execute(stmt).all():
            result[int(op_id)] = int(count)
        return result


def fetch_value_changes_for_row(
    session_factory: sessionmaker[Session],
    *,
    target_table: str,
    target_row_id: str,
    column: str | None = None,
) -> list[LineageValueChange]:
    """Return every value-change row for ``(target_table, target_row_id)``.

    Args:
        session_factory: SQLAlchemy session factory.
        target_table: Fully-qualified UC name of the target table.
        target_row_id: ``_lineage_row_id`` of the target row.
        column: When given, narrow to one column.

    Returns:
        All matching changes, ordered by ``created_at`` ascending so
        the oldest update appears first.  A single re-run that
        touched N columns of one row produces N rows with the same
        ``op_id``.
    """
    with session_factory() as session:
        stmt = select(LineageValueChange).where(
            LineageValueChange.target_table == target_table,
            LineageValueChange.target_row_id == target_row_id,
        )
        if column is not None:
            stmt = stmt.where(LineageValueChange.target_column == column)
        stmt = stmt.order_by(LineageValueChange.created_at.asc())
        return list(session.scalars(stmt))
