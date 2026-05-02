"""Lineage retention pruner.

Five lineage tables grow proportionally with run count:

* ``lineage_row_edges``.3, per-row provenance edges.
* ``lineage_row_rejects``.3, rejected merge rows.
* ``lineage_column_map``.1, per-column edges.
* ``lineage_value_changes``.1, per-cell value diffs.
* (``unattributed_writes`` from  stays out — its volume
  is dominated by detection cadence, not run count, so a TTL adds
  little.)

The pruner deletes rows older than per-table thresholds set on
:class:`pointlessql.settings.LineageRetentionSettings`.  ``None`` on
a per-table threshold means "never prune that axis".  Defaults
follow the  plan: row_edges 365d, row_rejects 365d,
value_changes 730d, column_map forever.

Each per-axis prune emits one ``audit_log`` row plus one
``pointlessql.lineage.pruned`` governance CloudEvent so the
forwarder fan-out sees the deletion.  Pruning is
itself auditable.

The function runs inside the existing scheduler.   also
ships an ``ensure_lineage_prune_job`` lifespan helper that upserts
a ``kind="lineage_prune"`` row in ``jobs`` so the prune lives next
to user-authored jobs (visible in ``/jobs``, can be paused).
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete

from pointlessql.models.lineage import (
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
)
from pointlessql.services import audit as audit_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.settings import Settings

logger = logging.getLogger(__name__)


_AXIS_TO_MODEL: dict[str, type] = {
    "row_edges": LineageRowEdge,
    "row_rejects": LineageRowReject,
    "column_map": LineageColumnMap,
    "value_changes": LineageValueChange,
}


def _resolve_threshold(settings: Settings, axis: str) -> int | None:
    """Return the configured retention-day threshold for *axis*, or ``None``.

    Args:
        settings: Resolved :class:`Settings` instance.
        axis: One of the four lineage-table axes.

    Returns:
        Day count or ``None`` (never prune).
    """
    retention = settings.audit.lineage_retention
    return {
        "row_edges": retention.row_edges_days,
        "row_rejects": retention.row_rejects_days,
        "column_map": retention.column_map_days,
        "value_changes": retention.value_changes_days,
    }[axis]


def _delete_older_than(
    session: Session,
    *,
    model: type,
    cutoff: datetime.datetime,
) -> int:
    """Delete rows whose ``created_at < cutoff``; return the affected count.

    Args:
        session: Open SQLAlchemy session (caller commits).
        model: ORM class with a ``created_at`` column.
        cutoff: UTC threshold; rows strictly older are deleted.

    Returns:
        Number of rows deleted.
    """
    stmt = delete(model).where(model.created_at < cutoff)
    result = session.execute(stmt)
    rowcount = getattr(result, "rowcount", 0) or 0
    return int(rowcount)


def prune_once(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    now: datetime.datetime | None = None,
) -> dict[str, int]:
    """Run a single prune pass over the four lineage tables.

    Args:
        session_factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings` (used for per-axis
            thresholds + the audit-stream toggle).
        now: Override for the cutoff anchor (testing hook).

    Returns:
        ``{axis: deleted_row_count}`` for every axis that ran.
        Axes whose threshold is ``None`` are absent from the dict.
    """
    anchor = now or datetime.datetime.now(datetime.UTC)
    deleted: dict[str, int] = {}

    for axis, model in _AXIS_TO_MODEL.items():
        threshold = _resolve_threshold(settings, axis)
        if threshold is None or threshold <= 0:
            continue
        cutoff = anchor - datetime.timedelta(days=threshold)
        try:
            with session_factory() as session:
                count = _delete_older_than(session, model=model, cutoff=cutoff)
                session.commit()
        except Exception:  # noqa: BLE001 — never raise into the scheduler
            logger.exception("lineage_pruner: %s prune failed", axis)
            continue
        deleted[axis] = count
        try:
            audit_service.log_action(
                session_factory,
                0,
                "system:lineage_pruner",
                "lineage_prune",
                f"lineage_{axis}",
                {
                    "deleted": count,
                    "cutoff": cutoff.isoformat(),
                    "threshold_days": threshold,
                },
                actor_role="system",
            )
        except Exception:  # noqa: BLE001 — audit-log is best-effort
            logger.exception("lineage_pruner: audit_log append failed for %s", axis)

    return deleted


async def prune_once_async(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    now: datetime.datetime | None = None,
) -> dict[str, int]:
    """Async wrapper around :func:`prune_once` that emits governance events.

    Splits the sync prune (DB I/O) from the async fan-out so the
    governance event fires per axis once we have the row count.

    Args:
        session_factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.
        now: Override for the cutoff anchor (testing hook).

    Returns:
        ``{axis: deleted_row_count}`` mirroring :func:`prune_once`.
    """
    import asyncio

    deleted = await asyncio.to_thread(prune_once, session_factory, settings, now=now)

    if not deleted:
        return deleted

    from pointlessql.services.governance_events import (
        EVENT_TYPE_LINEAGE_PRUNED,
        emit_governance_event,
    )

    for axis, count in deleted.items():
        if count <= 0:
            continue
        try:
            await emit_governance_event(
                EVENT_TYPE_LINEAGE_PRUNED,
                {
                    "axis": axis,
                    "deleted": count,
                    "threshold_days": _resolve_threshold(settings, axis),
                },
                settings=settings,
                session_factory=session_factory,
            )
        except Exception:  # noqa: BLE001 — emit must never raise
            logger.exception("lineage_pruner: emit failed for %s", axis)

    return deleted
