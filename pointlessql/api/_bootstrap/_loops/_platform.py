"""Platform-maintenance background-task coroutines started by the lifespan.

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
from pointlessql.services import audit as audit_service

logger = logging.getLogger(__name__)


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
