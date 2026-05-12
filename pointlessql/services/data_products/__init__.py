"""Data-product feature services (Phase 72)."""

from __future__ import annotations

from pointlessql.services.data_products.activity import (
    ActivityRow,
    fetch_activity_for_dp,
)
from pointlessql.services.data_products.badges import (
    compute_badges_bulk,
    compute_badges_for_dp,
)
from pointlessql.services.data_products.trending import (
    fetch_trending,
    refresh_trending,
)

__all__ = [
    "ActivityRow",
    "compute_badges_bulk",
    "compute_badges_for_dp",
    "fetch_activity_for_dp",
    "fetch_trending",
    "refresh_trending",
]
