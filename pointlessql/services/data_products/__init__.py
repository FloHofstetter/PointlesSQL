"""Data-product feature services (Phase 72 + Phase 73)."""

from __future__ import annotations

from pointlessql.services.data_products.activity import (
    ActivityRow,
    fetch_activity_for_dp,
)
from pointlessql.services.data_products.badges import (
    compute_badges_bulk,
    compute_badges_for_dp,
)
from pointlessql.services.data_products.passport import (
    refresh_passport_for_dp,
    refresh_stale_passports,
    render_passport,
)
from pointlessql.services.data_products.promote import (
    build_draft_yaml,
    candidate_row_count,
    scan_candidates,
)
from pointlessql.services.data_products.trending import (
    fetch_trending,
    refresh_trending,
)

__all__ = [
    "ActivityRow",
    "build_draft_yaml",
    "candidate_row_count",
    "compute_badges_bulk",
    "compute_badges_for_dp",
    "fetch_activity_for_dp",
    "fetch_trending",
    "refresh_passport_for_dp",
    "refresh_stale_passports",
    "refresh_trending",
    "render_passport",
    "scan_candidates",
]
