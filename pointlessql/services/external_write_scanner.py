"""Walk Delta history and flag commits no PQL operation claims.

The PQL primitives stamp every Delta version they produce in
``agent_run_operations.delta_version_after``.  This service walks
``DeltaTable.history()`` per UC table and INSERT-OR-IGNOREs into
``unattributed_writes`` for every commit whose version is not
referenced — i.e. writes from raw ``deltalake.write_deltalake()``,
Spark, ``cp`` of parquet files, or any other foreign tool.

Detection-only.  See
``project_full_autonomous_audit_critical_path.md`` for the
hard-block alternative deferred to Phase 16+.

The scanner reuses the
:func:`pointlessql.services.table_stats.read_delta_log_version`
pattern (``deltalake.DeltaTable(path)``) — no raw ``_delta_log/``
JSON parsing.  ``UNIQUE (table_fqn, delta_version)`` makes
re-scans idempotent so the periodic loop doesn't accumulate
duplicates.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import AgentRunOperation, UnattributedWrite

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 200


def _parse_commit_timestamp(entry: dict[str, Any]) -> datetime.datetime | None:
    """Parse a Delta history entry's ``timestamp`` field into UTC.

    Delta returns the timestamp as epoch milliseconds (int).  Older
    deltalake versions sometimes return a string ISO date; handle
    both.

    Args:
        entry: One ``DeltaTable.history()`` dict.

    Returns:
        Timezone-aware UTC ``datetime`` or ``None`` when the field
        is absent / unparseable.
    """
    raw = entry.get("timestamp")
    if raw is None:
        return None
    if isinstance(raw, int | float):
        try:
            return datetime.datetime.fromtimestamp(raw / 1000.0, tz=datetime.UTC)
        except OverflowError, OSError, ValueError:
            return None
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _attributed_versions(
    session: Session,
    table_fqn: str,
) -> set[int]:
    """Return Delta versions claimed by any ``agent_run_operations`` row.

    The scanner asks once per table; the set is small (one int per
    op that touched the table) so an in-memory diff is cheaper than
    a per-version round-trip.

    Args:
        session: Live SQLAlchemy session.
        table_fqn: Three-part UC name to filter on.

    Returns:
        The set of attributed Delta versions.
    """
    rows = session.scalars(
        select(AgentRunOperation.delta_version_after).where(
            AgentRunOperation.target_table == table_fqn,
            AgentRunOperation.delta_version_after.is_not(None),
        )
    ).all()
    return {int(v) for v in rows if v is not None}


def scan_table(
    factory: sessionmaker[Session],
    *,
    table_fqn: str,
    storage_location: str,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    now: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Scan one Delta table's history and INSERT-OR-IGNORE unattributed commits.

    Args:
        factory: SQLAlchemy session factory.
        table_fqn: Three-part UC name (``catalog.schema.table``).
        storage_location: Filesystem path or URI of the Delta table.
        history_limit: Cap on ``DeltaTable.history()`` entries
            inspected per call.  Bounds the per-tick cost on busy
            tables; the periodic loop catches up over multiple
            ticks.
        now: Override for the ``detected_at`` timestamp (testing
            hook).  ``None`` uses ``datetime.now(UTC)``.

    Returns:
        One dict per newly-persisted ``unattributed_writes`` row,
        shape ``{table_fqn, delta_version,
        commit_timestamp, detected_at, operation}``.  Empty list
        when no new rows were inserted; idempotent re-scans always
        return ``[]``.  Callers that just want the count can do
        ``len(scan_table(...))``.
    """
    import deltalake

    detected_at = now or datetime.datetime.now(datetime.UTC)
    try:
        table = deltalake.DeltaTable(storage_location)
        history = table.history(limit=history_limit)
    except Exception as exc:  # noqa: BLE001 — Delta absent / permission denied / corrupt
        logger.warning(
            "external_write_scanner: could not read history for %r at %r: %s",
            table_fqn,
            storage_location,
            exc,
        )
        return []

    if not history:
        return []

    inserted: list[dict[str, Any]] = []
    with factory() as session:
        attributed = _attributed_versions(session, table_fqn)
        for entry in history:
            version_raw = entry.get("version")
            if not isinstance(version_raw, int):
                continue
            if version_raw in attributed:
                continue
            commit_ts = _parse_commit_timestamp(entry)
            row = UnattributedWrite(
                table_fqn=table_fqn,
                delta_version=version_raw,
                commit_timestamp=commit_ts,
                commit_info=json.dumps(entry, default=str),
                detected_at=detected_at,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                # Already recorded by an earlier scan — UNIQUE
                # (table_fqn, delta_version) makes re-scans idempotent.
                session.rollback()
                continue
            inserted.append(
                {
                    "table_fqn": table_fqn,
                    "delta_version": version_raw,
                    "commit_timestamp": commit_ts.isoformat() if commit_ts else None,
                    "detected_at": detected_at.isoformat(),
                    "operation": entry.get("operation"),
                }
            )
        session.commit()
    return inserted


async def scan_all(
    factory: sessionmaker[Session],
    uc: UnityCatalogClient,
    *,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> int:
    """Iterate every UC table and scan each one's Delta history.

    Each newly-persisted ``unattributed_writes`` row also fires one
    ``pointlessql.external_write.detected`` governance CloudEvent so
    audit-stream sinks (Slack, S3 archive, CloudTrail) see the
    detection in real time.  Emit failures are logged but never
    raised — the persisted row is the source of truth, the event is
    a courtesy.

    Args:
        factory: SQLAlchemy session factory.
        uc: Async UC facade (used to enumerate catalogs / schemas /
            tables).
        history_limit: Forwarded to :func:`scan_table`.

    Returns:
        Sum of inserted ``unattributed_writes`` rows across every
        scanned table.
    """
    import asyncio

    from pointlessql.services.governance_events import (
        EVENT_TYPE_EXTERNAL_WRITE,
        emit_governance_event,
    )

    total = 0
    catalogs = await uc.list_catalogs()
    for catalog in catalogs:
        cat_name = catalog.get("name") if isinstance(catalog, dict) else None
        if not cat_name:
            continue
        try:
            schemas = await uc.list_schemas(cat_name)
        except Exception:  # noqa: BLE001 — skip per-catalog failures
            logger.exception("external_write_scanner: list_schemas failed for %r", cat_name)
            continue
        for schema in schemas:
            sch_name = schema.get("name") if isinstance(schema, dict) else None
            if not sch_name:
                continue
            try:
                tables = await uc.list_tables(cat_name, sch_name)
            except Exception:  # noqa: BLE001 — skip per-schema failures
                logger.exception(
                    "external_write_scanner: list_tables failed for %s.%s",
                    cat_name,
                    sch_name,
                )
                continue
            for table in tables:
                if not isinstance(table, dict):
                    continue
                tbl_name = table.get("name")
                storage = table.get("storage_location")
                if not isinstance(tbl_name, str) or not isinstance(storage, str) or not storage:
                    continue
                fqn = f"{cat_name}.{sch_name}.{tbl_name}"
                new_rows = await asyncio.to_thread(
                    scan_table,
                    factory,
                    table_fqn=fqn,
                    storage_location=storage,
                    history_limit=history_limit,
                )
                total += len(new_rows)
                for entry in new_rows:
                    try:
                        await emit_governance_event(
                            EVENT_TYPE_EXTERNAL_WRITE,
                            entry,
                            session_factory=factory,
                        )
                    except Exception:  # noqa: BLE001 — emit must never raise
                        logger.exception(
                            "external_write_scanner: emit failed for %s v%s",
                            entry.get("table_fqn"),
                            entry.get("delta_version"),
                        )
    return total


def list_unattributed(
    factory: sessionmaker[Session],
    *,
    only_unacknowledged: bool = False,
    table_fqn_like: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent ``unattributed_writes`` rows as dicts.

    Args:
        factory: SQLAlchemy session factory.
        only_unacknowledged: When ``True`` filter to rows whose
            ``acknowledged_at`` is ``NULL``.
        table_fqn_like: Optional ``LIKE``-style substring filter on
            ``table_fqn``.  ``None`` returns all.
        limit: Hard row cap; ORDER BY ``detected_at DESC`` so the
            newest rows are at the top.

    Returns:
        A list of dicts ready for the admin page template.
    """
    stmt = select(UnattributedWrite).order_by(UnattributedWrite.detected_at.desc()).limit(limit)
    if only_unacknowledged:
        stmt = stmt.where(UnattributedWrite.acknowledged_at.is_(None))
    if table_fqn_like:
        like_pattern = f"%{table_fqn_like}%"
        stmt = stmt.where(UnattributedWrite.table_fqn.like(like_pattern))
    with factory() as session:
        rows = session.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "table_fqn": r.table_fqn,
                "delta_version": r.delta_version,
                "commit_timestamp": r.commit_timestamp.isoformat() if r.commit_timestamp else None,
                "commit_info": r.commit_info,
                "detected_at": r.detected_at.isoformat(),
                "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                "acknowledged_by": r.acknowledged_by,
            }
            for r in rows
        ]


def acknowledge(
    factory: sessionmaker[Session],
    write_id: int,
    *,
    acknowledged_by: str,
    now: datetime.datetime | None = None,
) -> bool:
    """Mark one ``unattributed_writes`` row as reviewed.

    Args:
        factory: SQLAlchemy session factory.
        write_id: ``unattributed_writes.id`` to acknowledge.
        acknowledged_by: Email of the admin clicking the button.
        now: Override for the ``acknowledged_at`` timestamp
            (testing hook).

    Returns:
        ``True`` when the row existed and was updated; ``False``
        when missing.
    """
    timestamp = now or datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.get(UnattributedWrite, write_id)
        if row is None:
            return False
        row.acknowledged_at = timestamp
        row.acknowledged_by = acknowledged_by
        session.commit()
        return True


def count_unacknowledged(factory: sessionmaker[Session]) -> int:
    """Return the number of ``unattributed_writes`` rows awaiting review.

    Powers the admin sidebar badge.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``COUNT(*)`` of rows whose ``acknowledged_at`` is ``NULL``.
    """
    from sqlalchemy import func

    with factory() as session:
        stmt = (
            select(func.count())
            .select_from(UnattributedWrite)
            .where(UnattributedWrite.acknowledged_at.is_(None))
        )
        result = session.execute(stmt)
        return int(result.scalar() or 0)
