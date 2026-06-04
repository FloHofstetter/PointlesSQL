"""lineage-freshness compute + emit.

The pure helpers in this module turn ``expected_lineage_inbound``
rows into a per-row freshness verdict.  A registered expectation is
``fresh`` when the latest inbound edge from ``producer`` into
``target_table_full_name`` is younger than ``max_silence_minutes``,
``stale`` otherwise, and ``never_seen`` when no inbound edge has
ever landed for the pair.

The compute is **stateless** — the caller passes ``now`` so unit
tests can pin time, and the result is a list of dicts that the
admin UI / table-detail page can render directly.  Persistent
re-alert suppression uses ``ExpectedLineageInbound.last_alerted_at``.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pointlessql.models import ExpectedLineageInbound, LineageColumnMap
from pointlessql.types import SessionFactory

logger = logging.getLogger(__name__)



# Status enum surfaced on freshness rows.
STATUS_FRESH = "fresh"
STATUS_STALE = "stale"
STATUS_NEVER_SEEN = "never_seen"
STATUS_INACTIVE = "inactive"


def compute_freshness(
    session: Session,
    *,
    workspace_id: int,
    now: datetime.datetime,
    target_table_full_name: str | None = None,
    only_active: bool = True,
) -> list[dict[str, Any]]:
    """Return per-expectation freshness verdicts.

    Args:
        session: Open SQLAlchemy session.
        workspace_id: Filter rows to this workspace.
        now: Reference timestamp for the staleness comparison.  Tests
            pin this; production passes ``datetime.now(UTC)``.
        target_table_full_name: When supplied, restricts to one
            table's expectations (used by the table-detail card).
            ``None`` returns all expectations in the workspace.
        only_active: When True (default), excludes ``is_active=False``
            rows.  Admin pages may pass False to render the full
            registry including paused entries.

    Returns:
        List of dicts of shape
        ``{id, target_table_full_name, producer, max_silence_minutes,
        is_active, status, last_seen_at, stale_minutes, last_alerted_at}``
        ordered (stale first, never-seen second, fresh last).
    """
    stmt = select(ExpectedLineageInbound).where(ExpectedLineageInbound.workspace_id == workspace_id)
    if only_active:
        stmt = stmt.where(ExpectedLineageInbound.is_active.is_(True))
    if target_table_full_name is not None:
        stmt = stmt.where(ExpectedLineageInbound.target_table_full_name == target_table_full_name)
    expectations = list(session.scalars(stmt).all())
    if not expectations:
        return []

    # Single grouped lookup for all (target_table, producer) pairs in
    # one round-trip rather than N separate queries.
    pairs = {(e.target_table_full_name, e.producer) for e in expectations}
    last_seen_map: dict[tuple[str, str], datetime.datetime] = {}
    if pairs:
        target_tables = {t for (t, _) in pairs}
        producers = {p for (_, p) in pairs}
        last_seen_stmt = (
            select(
                LineageColumnMap.target_table,
                LineageColumnMap.producer,
                func.max(LineageColumnMap.created_at),
            )
            .where(
                LineageColumnMap.target_table.in_(target_tables),
                LineageColumnMap.producer.in_(producers),
                LineageColumnMap.workspace_id == workspace_id,
            )
            .group_by(LineageColumnMap.target_table, LineageColumnMap.producer)
        )
        for tbl, prd, max_at in session.execute(last_seen_stmt).all():
            if max_at is None or prd is None:
                continue
            last_seen_map[(str(tbl), str(prd))] = max_at

    rows: list[dict[str, Any]] = []
    for exp in expectations:
        if not exp.is_active:
            status = STATUS_INACTIVE
            stale_minutes: float | None = None
            last_seen = last_seen_map.get((exp.target_table_full_name, exp.producer))
        else:
            last_seen = last_seen_map.get((exp.target_table_full_name, exp.producer))
            if last_seen is None:
                status = STATUS_NEVER_SEEN
                stale_minutes = None
            else:
                # Treat naive (SQLite) datetimes as UTC.
                seen_utc = (
                    last_seen
                    if last_seen.tzinfo is not None
                    else last_seen.replace(tzinfo=datetime.UTC)
                )
                age_seconds = (now - seen_utc).total_seconds()
                stale_minutes = max(0.0, age_seconds / 60.0)
                if stale_minutes > exp.max_silence_minutes:
                    status = STATUS_STALE
                else:
                    status = STATUS_FRESH
        rows.append(
            {
                "id": exp.id,
                "target_table_full_name": exp.target_table_full_name,
                "producer": exp.producer,
                "max_silence_minutes": exp.max_silence_minutes,
                "is_active": exp.is_active,
                "status": status,
                "last_seen_at": last_seen,
                "stale_minutes": stale_minutes,
                "last_alerted_at": exp.last_alerted_at,
            }
        )

    _STATUS_ORDER = {
        STATUS_STALE: 0,
        STATUS_NEVER_SEEN: 1,
        STATUS_FRESH: 2,
        STATUS_INACTIVE: 3,
    }
    rows.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 9), r["target_table_full_name"]))
    return rows


def fresh_envelope(
    *,
    target_table_full_name: str,
    producer: str,
    workspace_id: int,
    stale_minutes: float | None,
    last_seen_at: datetime.datetime | None,
    fired_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for one staleness alert.

    Args:
        target_table_full_name: Three-part UC name with the gap.
        producer: OL ``job.namespace`` of the silent upstream feed.
        workspace_id: Workspace the registered expectation belongs to.
        stale_minutes: Wall-clock age of the silence in minutes, or
            ``None`` when no edge has ever been seen.
        last_seen_at: Wall-clock of the last inbound edge (``None``
            for ``never_seen``).
        fired_at: UTC timestamp the envelope was assembled.

    Returns:
        A plain dict ready to JSON-serialise onto the wire with
        ``Content-Type: application/cloudevents+json``.
    """
    return {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "source": f"/pointlessql/lineage/freshness/{producer}",
        "type": "pointlessql.lineage.freshness.stale",
        "time": fired_at.astimezone(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": target_table_full_name,
        "data": {
            "kind": "lineage_break",
            "producer": producer,
            "table": target_table_full_name,
            "stale_minutes": stale_minutes,
            "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
            "workspace_id": workspace_id,
        },
    }


def select_alert_candidates(
    rows: Iterable[dict[str, Any]],
    *,
    now: datetime.datetime,
    suppress_for_minutes_factor: float = 1.0,
) -> list[dict[str, Any]]:
    """Filter freshness rows down to those needing an alert dispatch.

    A row is a candidate when:

    * ``status`` is ``stale`` or ``never_seen``, AND
    * ``last_alerted_at`` is None OR
      ``last_alerted_at < now - max_silence_minutes * factor``.

    The factor lets the caller widen the suppression window beyond
    one max_silence interval — production may want a 2× factor so a
    flapping producer doesn't generate two alerts in quick succession.

    Args:
        rows: Output of :func:`compute_freshness`.
        now: Reference timestamp for the suppression comparison.
        suppress_for_minutes_factor: Multiplier on
            ``max_silence_minutes`` to derive the suppression cooldown.

    Returns:
        Subset of *rows* that should trigger a fresh alert envelope.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        status = row.get("status")
        if status not in (STATUS_STALE, STATUS_NEVER_SEEN):
            continue
        last_alerted = row.get("last_alerted_at")
        if last_alerted is None:
            out.append(row)
            continue
        cooldown_minutes = float(row["max_silence_minutes"]) * suppress_for_minutes_factor
        last_alerted_utc = (
            last_alerted
            if last_alerted.tzinfo is not None
            else last_alerted.replace(tzinfo=datetime.UTC)
        )
        if (now - last_alerted_utc).total_seconds() / 60.0 >= cooldown_minutes:
            out.append(row)
    return out


def stamp_alerted(
    session_factory: SessionFactory,
    *,
    expectation_ids: Iterable[int],
    fired_at: datetime.datetime,
) -> int:
    """Bump ``last_alerted_at`` on the listed expectations.

    Args:
        session_factory: Sessionmaker callable.
        expectation_ids: ``ExpectedLineageInbound.id`` values that
            just had an alert dispatched.
        fired_at: UTC timestamp to record as the alert time.

    Returns:
        Count of rows updated.
    """
    ids = [int(i) for i in expectation_ids]
    if not ids:
        return 0
    with session_factory() as session:
        result = session.execute(
            update(ExpectedLineageInbound)
            .where(ExpectedLineageInbound.id.in_(ids))
            .values(last_alerted_at=fired_at)
        )
        session.commit()
        return result.rowcount or 0


__all__ = [
    "STATUS_FRESH",
    "STATUS_INACTIVE",
    "STATUS_NEVER_SEEN",
    "STATUS_STALE",
    "compute_freshness",
    "fresh_envelope",
    "select_alert_candidates",
    "stamp_alerted",
]
