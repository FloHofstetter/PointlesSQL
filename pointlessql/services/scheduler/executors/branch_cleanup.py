# pyright: reportUnusedFunction=false
"""``branch_cleanup`` job kind — discard stale branches past their retention."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.config import Settings
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _branch_cleanup_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run the  branch auto-cleanup pass.

    Walks UC schemas, picks ``status='active'`` branches past the
    configured retention, and discards them.  Default-disabled — the
    underlying :func:`cleanup_old_branches` short-circuits when
    ``settings.branch.auto_cleanup_enabled`` is false.

    Runs the sync helper inside :func:`asyncio.to_thread` so the
    sync ``discard_branch_schema`` (which itself emits CloudEvents
    via the running loop) doesn't fight the scheduler's loop with
    nested ``asyncio.run`` calls.

    Args:
        job_run_id: Current run id (unused; the cleanup writes its
            own audit-log rows per discard).
        user_info: Run-as user (unused; cleanup runs without a
            principal-scoped audit run).
        config: Reserved for future per-job overrides.  Currently
            unused — all knobs come from settings.
        uc_client: Principal-forwarded facade (we use the underlying
            client for its sync transport).
    """
    del job_run_id, user_info, config

    from pointlessql.services.branch_cleanup import cleanup_old_branches

    settings = Settings()
    summary = await asyncio.to_thread(
        cleanup_old_branches,
        client=uc_client._client,  # noqa: SLF001 — sync soyuz client  # pyright: ignore[reportPrivateUsage]
        settings=settings,
    )
    logger.info("branch_cleanup_executor: %s", summary)
