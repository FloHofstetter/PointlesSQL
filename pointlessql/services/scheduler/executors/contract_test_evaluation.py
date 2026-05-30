# pyright: reportUnusedFunction=false
"""``contract_test_evaluation`` job kind — run a product's contract tests.

Config shape: ``{"data_product_id": <int>, "mode": "live"|"synthetic"}``.
Mode defaults to ``synthetic`` so the executor never wedges on missing
UC credentials in the scheduler tenant.

The job is opt-in via the scheduler UI; we do not auto-register a cron
entry — owners typically schedule one per product after declaring at
least one assertion.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _contract_test_evaluation_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run every enabled contract test for ``config['data_product_id']``."""
    del job_run_id, uc_client
    raw_id = config.get("data_product_id")
    if not isinstance(raw_id, int):
        raise ValidationError(
            "contract_test_evaluation requires config.data_product_id (int)"
        )
    mode = str(config.get("mode") or "synthetic")
    user_id = int(user_info.get("id") or 0)
    user_email = str(user_info.get("email") or "system")

    from pointlessql.db import get_session_factory
    from pointlessql.services.contract_tests import run_contract_tests

    factory = get_session_factory()

    def _work() -> dict[str, int]:
        outcome = run_contract_tests(
            factory,
            data_product_id=raw_id,
            mode=mode,
            user_id=user_id,
            user_email=user_email,
        )
        return {
            "total": outcome.total,
            "passed": outcome.passed,
            "failed": outcome.failed,
            "errored": outcome.errored,
        }

    summary = await asyncio.to_thread(_work)
    logger.info(
        "contract_test_evaluation_executor: product=%d mode=%s %s",
        raw_id,
        mode,
        summary,
    )
