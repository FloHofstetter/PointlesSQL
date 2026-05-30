# pyright: reportUnusedFunction=false
"""``cost_rollup_hourly`` job kind — bucket raw cost rows into hourlies.

Drains :class:`DataProductQueryCost` rows produced by the meter into
:class:`DataProductCostBucketHourly` so the dashboard + quota
aggregator can answer in O(buckets) instead of O(raw queries).  The
rollup is idempotent — re-running over the same window upserts the
existing bucket rather than duplicating it.

The job is auto-registered with no built-in cron entry; operators
opt-in by adding a job row with ``kind='cost_rollup_hourly'`` and a
1-hour interval.  Single-tenant installs without traffic see no
scheduler activity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _cost_rollup_hourly_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Roll the last hour's raw rows into the bucket table.

    Args:
        job_run_id: Current run id (unused; the rollup stamps
            ``bucket_hour`` on the upserted row instead).
        user_info: Run-as user (unused — rollup is workspace-wide).
        config: Reserved for future per-job overrides.  Currently
            unused.
        uc_client: Principal-forwarded facade (unused — rollup never
            touches Unity Catalog).
    """
    del job_run_id, user_info, config, uc_client

    from pointlessql.db import get_session_factory
    from pointlessql.services.cost import roll_up_hourly_buckets

    factory = get_session_factory()

    def _work() -> int:
        return roll_up_hourly_buckets(factory)

    written = await asyncio.to_thread(_work)
    logger.info("cost_rollup_hourly_executor: wrote %d bucket row(s)", written)
