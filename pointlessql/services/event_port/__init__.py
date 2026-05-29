"""Event-stream output-port service layer.

The runtime ships in three halves:

* **Substrate** — durable subscriptions + delivery ledger
  (:mod:`._subscription_crud`).  Lives in the metadata DB; tested in
  isolation.
* **Reader + hub** — :mod:`._cdf_reader` reads Delta CDF windows;
  :mod:`._ws_hub` keeps the in-memory broadcast hubs that fan rows out
  to live WebSocket subscribers.
* **Pump** — :mod:`._pump` is the scheduler-driven loop that advances
  every active subscription cursor one tick at a time and broadcasts
  via the hub.  Gated by :class:`EventPortSettings.enabled`.
"""

from __future__ import annotations

from pointlessql.services.event_port._cdf_reader import ChangeRow, read_changes
from pointlessql.services.event_port._pump import pump_all_active, pump_subscription
from pointlessql.services.event_port._subscription_crud import (
    advance_position,
    create_subscription,
    delete_subscription,
    list_subscriptions,
    pause_subscription,
    record_delivery,
    resume_subscription,
    rewind_subscription,
)

__all__ = [
    "ChangeRow",
    "advance_position",
    "create_subscription",
    "delete_subscription",
    "list_subscriptions",
    "pause_subscription",
    "pump_all_active",
    "pump_subscription",
    "read_changes",
    "record_delivery",
    "resume_subscription",
    "rewind_subscription",
]
