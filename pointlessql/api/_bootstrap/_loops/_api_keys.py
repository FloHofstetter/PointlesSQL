"""API-key background-task coroutines started by the lifespan.

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
