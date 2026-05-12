"""Background-task coroutines started by the lifespan.

Each coroutine is a long-running ``while True`` loop that performs
one bookkeeping pass per cadence and survives transient failures.
The lifespan in ``api.main`` schedules them as ``asyncio.Task``
instances at startup and cancels them at shutdown.

All seven loops share the same shape:

1. Snapshot the relevant settings sub-tree at start.
2. Loop forever; per tick: do work guarded by a broad ``except``,
   then sleep for the interval, then bail cleanly on
   ``asyncio.CancelledError``.

This module is private (``_bootstrap`` package).  ``main.py``
imports the loop functions directly; nothing else should call them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.config import Settings
from pointlessql.services import audit as audit_service

logger = logging.getLogger(__name__)

# The loop coroutines below are imported from ``main.py``'s
# ``_lifespan`` and scheduled as ``asyncio.Task``s — the underscore
# prefix on each name documents "do not call directly from
# anywhere except the lifespan startup" but the cross-module wiring
# IS intentional.  ``__all__`` makes pyright agree that these names
# are deliberately exported to ``main.py``.
__all__ = [
    "_audit_retention_loop",
    "_branch_cleanup_loop",
    "_cdf_tail_loop",
    "_data_product_freshness_loop",
    "_external_writes_loop",
    "_lineage_pruner_loop",
    "_workspace_repos_sync_loop",
]


async def _audit_retention_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Run ``cleanup_old_entries`` on a fixed cadence for the lifetime of the app.

    A separate task rather than a scheduler-kind keeps the
    cleanup path independent of the job scheduler — operators who
    disable the scheduler (``POINTLESSQL_SCHEDULER_ENABLED=false``)
    still want retention to run.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings` — only
            ``audit.retention_days`` and
            ``audit.cleanup_interval_seconds`` are read.
    """
    interval = max(60, settings.audit.cleanup_interval_seconds)
    retention = settings.audit.retention_days
    while True:
        try:
            await asyncio.to_thread(audit_service.cleanup_old_entries, factory, retention)
        except Exception:  # noqa: BLE001 — retention loop must survive everything
            logger.exception("audit: retention loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


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


async def _data_product_freshness_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic SLA scan across cached data products.

    Active only when
    ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS`` is explicitly
    non-zero — same opt-in discipline as the external-write scanner.
    Per tick, walks every :class:`DataProduct` row whose
    ``sla_minutes`` is set, observes the latest write timestamp via
    ``DeltaTable.history()``, and emits a
    ``pointlessql.data_product.sla_violated`` CloudEvent when the age
    exceeds the SLA.  ``last_alerted_at`` suppresses re-alerts within
    ``re_alert_suppress_minutes``.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        uc: ``UnityCatalogClient`` used to enumerate the product's
            tables (storage locations).
        settings: Snapshotted :class:`Settings` — only
            ``data_products.scan_interval_seconds`` and
            ``data_products.re_alert_suppress_minutes`` are read.
    """
    from pointlessql.services import data_product_freshness_scanner

    interval = max(60, settings.data_products.scan_interval_seconds)
    suppress = settings.data_products.re_alert_suppress_minutes
    while True:
        try:
            emitted = await data_product_freshness_scanner.scan_all(
                factory,
                uc,
                re_alert_suppress_minutes=suppress,
            )
            if emitted:
                logger.info(
                    "data_product_freshness: tick emitted %d sla_violated event(s)",
                    emitted,
                )
        except Exception:  # noqa: BLE001 — scanner loop must survive everything
            logger.exception("data_product_freshness: scan tick raised")
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


async def _workspace_repos_sync_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Periodic workspace-repo sync (Phase 51.4).

    Active only when
    ``POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS`` is non-zero — same
    opt-in discipline as every other Phase-13.x+ scanner.  Each
    tick lists the repos whose ``last_synced_at`` is older than
    the configured cadence (or ``NULL``) and pulls them
    sequentially.  Per-repo failures are recorded on the row
    itself; the loop never aborts because of a single bad upstream.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        settings: Snapshotted :class:`Settings` — only
            ``workspace_repos.*`` is read.
    """
    from datetime import UTC, datetime, timedelta

    from pointlessql.services.workspace.repos import (
        build_post_pull_loader_hook,
        list_repos_due_for_sync,
        sync_repo,
    )

    interval = max(60, settings.workspace_repos.sync_interval_seconds)
    base_dir = settings.workspace_repos.base_dir
    hook = build_post_pull_loader_hook(factory, settings=settings)
    while True:
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=interval)
            for repo in list_repos_due_for_sync(factory, cutoff=cutoff):
                try:
                    await sync_repo(
                        factory,
                        repo_id=repo.id,
                        base_dir=base_dir,
                        trigger="cron",
                        actor_user_id=None,
                        on_post_pull=hook,
                    )
                except Exception:  # noqa: BLE001 — per-repo failure isolation
                    # bare-broad-ok: sync persists the failure on the row;
                    # the loop must continue to the next repo regardless.
                    logger.exception("workspace_repos: cron sync of %s raised", repo.id)
        except Exception:  # noqa: BLE001 — outer-loop guard
            # bare-broad-ok: never let an unforeseen error kill the loop.
            logger.exception("workspace_repos: cron tick raised")
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
