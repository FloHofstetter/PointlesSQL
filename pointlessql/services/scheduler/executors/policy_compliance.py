# pyright: reportUnusedFunction=false
"""``policy_compliance`` job kind — scan products for policy drift.

Runs the deterministic governance checks (retention overdue,
unclassified PII-looking columns) across every product in the
workspace and logs findings to the audit log, where they surface in the
audit cockpit + each product's Governance tab.  Opt-in via the
scheduler UI; no default cron entry is auto-registered.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _policy_compliance_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Scan the workspace for policy-compliance drift.

    Args:
        job_run_id: Current run id (unused — findings land as audit
            rows, not on the job run).
        user_info: Run-as user; supplies the audit actor + the
            workspace to scan.
        config: Reserved for future per-job overrides; currently
            unused.
        uc_client: Principal-forwarded facade (unused — the scan
            resolves Delta tables through the sync soyuz client).
    """
    del job_run_id, uc_client

    from pointlessql.config import Settings
    from pointlessql.db import get_session_factory
    from pointlessql.services import governance as governance_service

    factory = get_session_factory()
    settings = Settings()
    workspace_id = int(config.get("workspace_id", 1) or 1)

    summary = await asyncio.to_thread(
        governance_service.scan_workspace,
        factory,
        settings,
        workspace_id=workspace_id,
        actor_user_id=int(user_info.get("id", 0) or 0),
        actor_email=user_info.get("email", "system"),
    )
    logger.info(
        "policy_compliance_executor: scanned %s products, %s violations",
        summary["products_scanned"],
        len(summary["violations"]),
    )
