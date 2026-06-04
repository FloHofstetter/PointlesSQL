"""Lineage / CDF / external-write background-task coroutines started by the lifespan.

Each coroutine is a long-running ``while True`` loop that performs one
bookkeeping pass per cadence and survives transient failures.  See the
package ``__init__`` for the shared shape; these are scheduled as
``asyncio.Task`` instances by the lifespan and cancelled at shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.config import Settings

logger = logging.getLogger(__name__)


async def _external_writes_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic scan for unattributed Delta commits.

    Active only when
    ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS`` is
    explicitly non-zero — the default keeps the loop dormant on
    single-node vServer deployments where per-table
    ``DeltaTable.history()`` cost adds up.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        uc: ``UnityCatalogClient`` used to enumerate tables.
        settings: Snapshotted :class:`Settings` — only
            ``external_writes.scan_interval_seconds`` and
            ``external_writes.history_limit`` are read.
    """
    from pointlessql.services import external_write_scanner

    interval = max(60, settings.external_writes.scan_interval_seconds)
    history_limit = settings.external_writes.history_limit
    while True:
        try:
            inserted = await external_write_scanner.scan_all(
                factory, uc, history_limit=history_limit
            )
            if inserted:
                logger.info(
                    "external_writes: scan tick recorded %d unattributed commit(s)",
                    inserted,
                )
        except Exception:  # noqa: BLE001 — scanner loop must survive everything
            logger.exception("external_writes: scan tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _cdf_tail_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic CDF tail across active subscriptions.

    Active only when
    ``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` is explicitly non-zero
    AND at least one :class:`CdfTailSubscription` row has
    ``is_active=True``.  Same opt-in discipline as the external-write
    scanner: zero-config installs see no extra Delta IO.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        uc: ``UnityCatalogClient`` used to resolve each
            subscription's ``storage_location`` per tick.
        settings: Snapshotted :class:`Settings` — only
            ``cdf_tail.interval_seconds`` and
            ``cdf_tail.history_limit`` are read.
    """
    from pointlessql.services import cdf_tail

    interval = max(60, settings.cdf_tail.interval_seconds)
    history_limit = settings.cdf_tail.history_limit
    while True:
        try:
            inserted = await cdf_tail.tail_all(factory, uc, history_limit=history_limit)
            if inserted:
                logger.info("cdf_tail: tick recorded %d new event(s)", inserted)
        except Exception:  # noqa: BLE001 — tail loop must survive everything
            logger.exception("cdf_tail: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _lineage_pruner_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Periodic prune of the four lineage tables.

    Active when at least one
    :class:`LineageRetentionSettings` axis has a positive
    ``*_days`` value.  The loop wakes every
    ``audit.cleanup_interval_seconds`` (default 86400 = 24h),
    matching the audit-log retention cadence — both run in the
    operator-quiet hours.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings`.
    """
    from pointlessql.services.lineage.pruner import prune_once_async

    interval = max(60, settings.audit.cleanup_interval_seconds)
    while True:
        try:
            deleted = await prune_once_async(factory, settings)
            if deleted:
                logger.info(
                    "lineage_pruner: pruned %s",
                    ", ".join(f"{axis}={count}" for axis, count in deleted.items()),
                )
        except Exception:  # noqa: BLE001 — pruner must survive everything
            logger.exception("lineage_pruner: prune tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _branch_cleanup_loop(  # pyright: ignore[reportUnusedFunction]
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic  branch auto-cleanup pass.

    Wakes once per ``audit.cleanup_interval_seconds`` (default
    24h), then either short-circuits (when
    ``branch.auto_cleanup_enabled=False``) or walks UC schemas and
    discards active branches past
    ``branch.auto_cleanup_retention_days``.  The 24h cadence is
    deliberately coarse — branch cleanup is a maintenance op, not a
    realtime concern.

    Args:
        uc: ``UnityCatalogClient`` whose underlying sync client
            drives the cleanup pass.
        settings: Snapshotted :class:`Settings`.
    """
    from pointlessql.services.branch_cleanup import cleanup_old_branches

    interval = max(60, settings.audit.cleanup_interval_seconds)
    while True:
        try:
            summary = await asyncio.to_thread(
                cleanup_old_branches,
                client=uc._client,  # noqa: SLF001 — sync soyuz client
                settings=settings,
            )
            if summary.get("deleted"):
                logger.info("branch_cleanup: %s", summary)
        except Exception:  # noqa: BLE001 — cleanup loop must survive everything
            logger.exception("branch_cleanup: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
