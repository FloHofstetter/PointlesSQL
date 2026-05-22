# pyright: reportUnusedFunction=false
"""``coedit_compaction`` job kind — compact stale ``notebook_crdt_state`` blobs.

Phase 105.8 executor for the co-edit hub.  The job is opt-in via the
scheduler UI; we deliberately do not auto-register a default cron entry
so single-worker installs without the bus see no scheduler activity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _coedit_compaction_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Compact stale ``notebook_crdt_state`` blobs.

    Phase 105.8 — walk every ``notebook_crdt_state`` row, skip the
    notebooks that currently have a live Sprint-105.2 hub (the hub's
    own teardown flush handles those), and compact any inactive blob
    that has crossed the size or TTL gate exposed by
    :func:`coedit_service.needs_compaction`.

    Best-effort — per-row failures are logged but do not abort the
    pass.  The job is opt-in via the scheduler UI; we do not auto-
    register a default cron entry.

    Args:
        job_run_id: Current run id (unused; the compaction stamps
            ``compacted_at`` on the row instead of its own audit
            row).
        user_info: Run-as user (unused — compaction runs as a
            workspace-wide housekeeping pass).
        config: Reserved for future per-job overrides.  Currently
            unused.
        uc_client: Principal-forwarded facade (unused — compaction
            never touches Unity Catalog).
    """
    del job_run_id, user_info, config, uc_client

    from pointlessql.api import notebook_coedit_ws
    from pointlessql.db import get_session_factory
    from pointlessql.models.notebook import NotebookCrdtState
    from pointlessql.services.notebook import coedit as coedit_service

    factory = get_session_factory()

    def _work() -> dict[str, int]:
        compacted = 0
        skipped_active = 0
        skipped_below_threshold = 0
        failed = 0
        with factory() as session:
            rows = list(
                session.execute(select(NotebookCrdtState)).scalars().all()
            )
            for row in rows:
                if (
                    row.notebook_id
                    in notebook_coedit_ws._HUBS  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                ):
                    skipped_active += 1
                    continue
                if not coedit_service.needs_compaction(row):
                    skipped_below_threshold += 1
                    continue
                try:
                    coedit_service.compact(session, notebook_id=row.notebook_id)
                    session.commit()
                    compacted += 1
                except Exception:  # noqa: BLE001 — keep iterating
                    session.rollback()
                    failed += 1
                    logger.exception(
                        "coedit_compaction: compact failed for %s",
                        row.notebook_id,
                    )
        return {
            "compacted": compacted,
            "skipped_active": skipped_active,
            "skipped_below_threshold": skipped_below_threshold,
            "failed": failed,
        }

    summary = await asyncio.to_thread(_work)
    logger.info("coedit_compaction_executor: %s", summary)
