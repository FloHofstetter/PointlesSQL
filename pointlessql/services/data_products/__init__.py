"""Data-product feature services (Phase 72)."""

from __future__ import annotations

from pointlessql.services.data_products.activity import (
    ActivityRow,
    fetch_activity_for_dp,
)

__all__ = ["ActivityRow", "fetch_activity_for_dp"]
