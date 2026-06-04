"""Data-product background-task coroutines started by the lifespan.

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


async def _active_reviewer_loop(  # pyright: ignore[reportUnusedFunction]
    factory: Any,
    settings: Settings,
) -> None:
    """Active-reviewer daily tick.

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
