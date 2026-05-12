"""Per-user notification inbox + fan-out helpers (Phase 71.4)."""

from __future__ import annotations

from pointlessql.services.notifications.fanout import fanout_dataproduct_event

__all__ = ["fanout_dataproduct_event"]
