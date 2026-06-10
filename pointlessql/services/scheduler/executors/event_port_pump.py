# pyright: reportUnusedFunction=false
"""``event_port_pump`` job kind — fan Delta CDF rows out to subscribers.

Pumps every active :class:`DataProductEventSubscription` once.  Gated by
:class:`EventPortSettings.enabled` — when off, the executor exits
immediately so single-worker installs without event consumers see no
scheduler activity.
"""

from __future__ import annotations

import logging
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

_LOG = logging.getLogger(__name__)


async def _event_port_pump_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Pump every active event subscription once.

    Args:
        job_run_id: Current run id (unused — pumping records its own
            delivery ledger rows).
        user_info: Run-as user (unused — pumping is workspace-wide).
        config: Optional override:
            ``{"max_versions": int}`` to bound the per-tick window.
        uc_client: Principal-forwarded facade (unused — pump uses the
            generic soyuz client to resolve storage locations).
    """
    del job_run_id, user_info, uc_client

    from pointlessql.config import get_settings
    from pointlessql.db import get_session_factory
    from pointlessql.services.event_port._pump import pump_all_active

    settings = get_settings()
    event_port = getattr(settings, "event_port", None)
    if event_port is None or not getattr(event_port, "enabled", False):
        _LOG.debug("event_port_pump: disabled by settings — skipping tick")
        return

    max_versions = int(
        config.get("max_versions") or getattr(event_port, "cdf_max_versions_per_pump", 100)
    )
    factory = get_session_factory()
    summary = await pump_all_active(factory, max_versions=max_versions)
    _LOG.info("event_port_pump: %s", summary)
