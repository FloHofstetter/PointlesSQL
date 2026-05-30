# pyright: reportUnusedFunction=false
"""``entity_link_discovery`` job kind — scan for emergent same_as links.

Config shape: ``{"workspace_id": <int>, "threshold": <float>}``.  Both
keys are optional; defaults are workspace 1 + the threshold from
:mod:`pointlessql.services.entities._candidates`.

The job is opt-in via the scheduler UI; we do not auto-register a cron
entry — discovery is cheap but its review-queue produces stewardship
work that should be paced by the operator.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _entity_link_discovery_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run :func:`discover_candidates` for the configured workspace."""
    del job_run_id, user_info, uc_client
    workspace_id = int(config.get("workspace_id") or 1)
    threshold_raw = config.get("threshold")
    threshold = float(threshold_raw) if isinstance(threshold_raw, (int, float)) else None

    from pointlessql.db import get_session_factory
    from pointlessql.services.entities._candidates import (
        DEFAULT_CONFIDENCE_THRESHOLD,
        discover_candidates,
    )

    factory = get_session_factory()
    effective_threshold = threshold if threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD

    def _work() -> int:
        return discover_candidates(
            factory,
            workspace_id=workspace_id,
            threshold=effective_threshold,
        )

    inserted = await asyncio.to_thread(_work)
    logger.info(
        "entity_link_discovery_executor: workspace=%d threshold=%.2f inserted=%d",
        workspace_id,
        effective_threshold,
        inserted,
    )
