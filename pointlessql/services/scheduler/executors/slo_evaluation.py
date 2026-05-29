# pyright: reportUnusedFunction=false
"""``slo_evaluation`` job kind — evaluate product SLOs across a workspace.

Runs the SLO evaluator over every product and logs each failing
objective to the audit log, where it surfaces in the audit cockpit + the
product's SLO panel.  Opt-in via the scheduler UI; no default cron entry
is auto-registered.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _slo_evaluation_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Evaluate every product's SLOs and log failures.

    Args:
        job_run_id: Current run id (unused — findings land as audit
            rows, not on the job run).
        user_info: Run-as user; supplies the audit actor + the
            workspace to scan.
        config: Reserved for per-job overrides; reads ``workspace_id``
            (defaults to 1).
        uc_client: Principal-forwarded facade (unused — the evaluator
            reads the self-generated statistics, not Delta directly).
    """
    del job_run_id, uc_client

    from pointlessql.db import get_session_factory
    from pointlessql.services import slo as slo_service

    factory = get_session_factory()
    workspace_id = int(config.get("workspace_id", 1) or 1)

    summary = await asyncio.to_thread(
        slo_service.scan_workspace,
        factory,
        workspace_id=workspace_id,
        actor_user_id=int(user_info.get("id", 0) or 0),
        actor_email=user_info.get("email", "system"),
    )
    logger.info(
        "slo_evaluation_executor: scanned %s products, %s violations",
        summary["products_scanned"],
        len(summary["violations"]),
    )
