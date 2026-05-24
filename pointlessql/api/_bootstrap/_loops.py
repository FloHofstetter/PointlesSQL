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
    "_active_reviewer_loop",
    "_api_key_lifecycle_sweep_loop",
    "_api_key_usage_flush_loop",
    "_api_key_usage_retention_loop",
    "_audit_retention_loop",
    "_branch_cleanup_loop",
    "_cdf_tail_loop",
    "_data_product_cooccurrence_loop",
    "_data_product_freshness_loop",
    "_data_product_passport_loop",
    "_data_product_promotion_loop",
    "_data_product_trending_loop",
    "_external_writes_loop",
    "_lineage_pruner_loop",
    "_user_badges_loop",
    "_user_notification_digest_loop",
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


async def _api_key_usage_flush_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    app_state: Any,
    settings: Settings,
) -> None:
    """Flush the in-process usage Counter every ``usage_flush_interval_seconds``.

    Survives transient DB failures so a single bad commit can't lose
    the buffer beyond the current tick.

    Args:
        factory: SQLAlchemy session factory.
        app_state: ``app.state`` carrying the live ``api_key_usage_buffer``
            Counter.
        settings: Snapshotted :class:`Settings` — only
            ``api_key_acl.usage_flush_interval_seconds`` is read.
    """
    from pointlessql.services.api_keys._usage import flush_buffer

    interval = max(5, settings.api_key_acl.usage_flush_interval_seconds)
    while True:
        try:
            await asyncio.to_thread(flush_buffer, factory, app_state)
        except Exception:  # noqa: BLE001 — flush loop must survive everything
            logger.exception("api-keys: usage flush loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _api_key_usage_retention_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Prune ``api_key_usage_buckets`` rows older than the retention window.

    Daily cadence is plenty for a 30-day window; the loop just sleeps
    on its own short cadence and the underlying delete is a no-op when
    nothing's beyond the cutoff.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only
            ``api_key_acl.usage_retention_days`` is read.
    """
    from pointlessql.services.api_keys._usage import cleanup_stale_usage

    # Per-day cadence; tunable later if a deployment wants finer pruning.
    interval = 86_400
    retention = settings.api_key_acl.usage_retention_days
    while True:
        try:
            await asyncio.to_thread(cleanup_stale_usage, factory, retention_days=retention)
        except Exception:  # noqa: BLE001 — retention loop must survive everything
            logger.exception("api-keys: usage retention loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _api_key_lifecycle_sweep_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Run :func:`run_lifecycle_sweep` once per configured cadence.

    Marks expired keys (auto-quarantine if enabled) + emits one
    ``api_key.expiry_warning`` audit row per key entering the
    ``expiry_warning_days`` window.  Survives transient failures so a
    DB hiccup never takes the lifespan down.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only
            ``api_key_lifecycle.*`` is read.
    """
    from pointlessql.services.api_keys._lifecycle_sweep import run_lifecycle_sweep

    interval = max(60, settings.api_key_lifecycle.sweep_interval_seconds)
    warning_days = settings.api_key_lifecycle.expiry_warning_days
    quarantine = settings.api_key_lifecycle.quarantine_on_expiry
    while True:
        try:
            await asyncio.to_thread(
                run_lifecycle_sweep,
                factory,
                expiry_warning_days=warning_days,
                quarantine_on_expiry=quarantine,
            )
        except Exception:  # noqa: BLE001 — sweep loop must survive everything
            logger.exception("api-keys: lifecycle sweep loop tick raised")
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


async def _data_product_trending_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Refresh the cached "trending in agent workloads" view.

    Active only when ``data_products.trending_refresh_interval_seconds``
    is non-zero — same opt-in discipline as the freshness scanner.
    Per tick, recomputes the top-N rows per workspace for the
    rolling window and UPSERTs ``data_product_trending``.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only the
            ``data_products`` sub-tree is read.
    """
    from pointlessql.services.data_products import refresh_trending

    interval = max(60, settings.data_products.trending_refresh_interval_seconds)
    window_days = settings.data_products.trending_window_days
    top_n = settings.data_products.trending_top_n
    while True:
        try:
            inserted = await asyncio.to_thread(
                refresh_trending,
                factory,
                window_days=window_days,
                top_n=top_n,
            )
            if inserted:
                logger.info(
                    "data_product_trending: tick refreshed %d row(s)",
                    inserted,
                )
        except Exception:  # noqa: BLE001 — trending loop must survive everything
            logger.exception("data_product_trending: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _data_product_cooccurrence_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Cross-DP co-occurrence cache refresh.

    Active only when ``data_products.cooccurrence_enabled`` is
    true.  Per tick, recomputes the per-workspace pair counts
    over the rolling window and UPSERTs
    ``data_product_cooccurrence``.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only the
            ``data_products`` sub-tree is read.
    """
    from pointlessql.services.data_products import refresh_cooccurrence

    if not settings.data_products.cooccurrence_enabled:
        return

    interval = max(60, settings.data_products.cooccurrence_refresh_interval_seconds)
    window_days = settings.data_products.cooccurrence_window_days
    top_n = settings.data_products.cooccurrence_top_n
    while True:
        try:
            inserted = await asyncio.to_thread(
                refresh_cooccurrence,
                factory,
                window_days=window_days,
                top_n=top_n,
            )
            if inserted:
                logger.info(
                    "data_product_cooccurrence: tick refreshed %d row(s)",
                    inserted,
                )
        except Exception:  # noqa: BLE001 — cooccurrence loop must survive everything
            logger.exception("data_product_cooccurrence: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _data_product_passport_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Auto-passport stale-refresh loop.

    Active only when ``data_products.passport_loop_enabled`` is
    true.  Per tick, refreshes every DP whose latest passport
    is older than ``passport_loop_stale_threshold_seconds``.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only the
            ``data_products`` sub-tree is read.
    """
    from pointlessql.services.data_products import refresh_stale_passports

    if not settings.data_products.passport_loop_enabled:
        return

    interval = max(60, settings.data_products.passport_loop_interval_seconds)
    threshold = settings.data_products.passport_loop_stale_threshold_seconds
    while True:
        try:
            refreshed = await asyncio.to_thread(
                refresh_stale_passports,
                factory,
                stale_threshold_seconds=threshold,
            )
            if refreshed:
                logger.info(
                    "data_product_passport: tick refreshed %d row(s)",
                    refreshed,
                )
        except Exception:  # noqa: BLE001 — passport loop must survive everything
            logger.exception("data_product_passport: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _data_product_promotion_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Promote-to-DP candidate scanner.

    Active only when ``data_products.promote_enabled`` is true.
    Per tick, calls :func:`scan_candidates` to UPSERT the
    candidate cache so the ``/data-products/candidates`` page
    stays fresh without per-request recomputation.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only the
            ``data_products`` sub-tree is read.
    """
    from pointlessql.services.data_products import scan_candidates

    if not settings.data_products.promote_enabled:
        return

    interval = max(60, settings.data_products.promote_scan_interval_seconds)
    window_days = settings.data_products.promote_window_days
    min_runs = settings.data_products.promote_min_runs
    min_ops = settings.data_products.promote_min_ops
    while True:
        try:
            inserted = await asyncio.to_thread(
                scan_candidates,
                factory,
                window_days=window_days,
                min_runs=min_runs,
                min_ops=min_ops,
            )
            if inserted:
                logger.info(
                    "data_product_promotion: tick refreshed %d candidate(s)",
                    inserted,
                )
        except Exception:  # noqa: BLE001 — promotion loop must survive everything
            logger.exception("data_product_promotion: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _active_reviewer_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Phase 74 active-reviewer daily tick.

    Active only when
    ``data_products.active_reviewer_enabled`` is true.  Sleeps
    until the next ``active_reviewer_trigger_hour`` UTC boundary,
    then iterates every DP with
    ``DataProductActiveReviewerConfig.runner='inproc'``,
    rendering the prompt + calling the configured LLM provider
    + posting the result.

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — only the
            ``data_products`` sub-tree is read.
    """
    from pointlessql.services.data_products import (
        iter_opted_in_dp_ids,
        run_reviewer_for_dp,
    )
    from pointlessql.services.notifications import seconds_until_next_window

    if not settings.data_products.active_reviewer_enabled:
        return

    trigger_hour = settings.data_products.active_reviewer_trigger_hour
    provider_default = settings.data_products.active_reviewer_llm_provider
    model_default = settings.data_products.active_reviewer_model
    max_concurrent = max(1, settings.data_products.active_reviewer_max_concurrent)

    while True:
        try:
            wait = seconds_until_next_window(trigger_hour)
            await asyncio.sleep(wait)
            targets = await asyncio.to_thread(iter_opted_in_dp_ids, factory, runner="inproc")
            if not targets:
                continue
            sem = asyncio.Semaphore(max_concurrent)

            async def _one(ws_id: int, dp_id: int) -> None:
                async with sem:
                    try:
                        await run_reviewer_for_dp(
                            factory,
                            workspace_id=ws_id,
                            data_product_id=dp_id,
                            trigger="loop",
                            provider_default=provider_default,
                            model_default=model_default,
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "active_reviewer: dp=%s ws=%s tick raised",
                            dp_id,
                            ws_id,
                        )

            await asyncio.gather(*[_one(ws, dp) for ws, dp, _c, _s in targets])
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001 — reviewer loop must survive everything
            logger.exception("active_reviewer: outer tick raised")
        try:
            await asyncio.sleep(60)  # belt-and-braces wake-floor
        except asyncio.CancelledError:
            return


async def _user_badges_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Sticky reputation-badge recompute.

    Wakes once every 24 h, calls :func:`award_badges` to INSERT
    any newly-met badge thresholds, and sleeps again.  Badges are
    positive-only; the helper never deletes rows, so the loop is
    safe even if the underlying metric briefly regresses (e.g. a
    review is rolled back).

    Args:
        factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` — currently
            unused; reserved for a future ``social.badges_enabled``
            kill-switch.
    """
    del settings
    from pointlessql.services.social.badges import award_badges

    interval = 24 * 3600
    while True:
        try:
            inserted = await asyncio.to_thread(award_badges, factory)
            if inserted:
                logger.info("user_badges: awarded %d new badge(s)", inserted)
        except Exception:  # noqa: BLE001 — badges loop must survive everything
            logger.exception("user_badges: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _user_notification_digest_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Daily marketplace-digest delivery.

    Active only when ``notifications.digest_enabled`` is true (off
    by default).  Sleeps until the next ``digest_trigger_hour``
    UTC boundary, then calls :func:`fire_digests` to emit one
    ``pointlessql.notification.digest`` envelope per eligible user.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings` — only the
            ``notifications`` sub-tree is read.
    """
    from pointlessql.services.notifications import (
        fire_digests,
        seconds_until_next_window,
    )

    if not settings.notifications.digest_enabled:
        # Loop registers but stays inert; cheaper than skipping
        # registration entirely + lets the operator flip the env
        # var on without a restart by relying on a future "settings
        # reload" feature.  Until then we just no-op forever.
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return

    target_hour = settings.notifications.digest_trigger_hour
    while True:
        try:
            wait = seconds_until_next_window(target_hour)
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        try:
            emitted = await fire_digests(factory, settings)
            if emitted:
                logger.info("notification_digest: fired %d envelope(s)", emitted)
        except Exception:  # noqa: BLE001 — digest loop must survive everything
            logger.exception("notification_digest: tick raised")


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
    """Periodic workspace-repo sync.

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
