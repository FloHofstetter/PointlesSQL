"""Event-stream output-port service layer.

The runtime ships in two halves:

* **Substrate** (this module) — durable subscriptions + delivery
  ledger.  Lives in the metadata DB; tested in isolation.
* **Pump + WS hub** (deferred to a later phase) — the Delta-CDF reader
  + the in-memory broadcast hub that actually fans rows out to live
  consumers.  Gated by :class:`EventPortSettings.enabled`.

Today (Phase 133 substrate) the CRUD + position math + delivery
record-keeping are in place.  Wiring the real streaming endpoints
plugs in on top without schema churn.
"""

from __future__ import annotations

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
    "advance_position",
    "create_subscription",
    "delete_subscription",
    "list_subscriptions",
    "pause_subscription",
    "record_delivery",
    "resume_subscription",
    "rewind_subscription",
]
