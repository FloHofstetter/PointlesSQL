"""Data-product feature services."""

from __future__ import annotations

from pointlessql.services.data_products.active_reviewer import (
    ReviewVerdict,
    build_prompt,
    iter_opted_in_dp_ids,
    parse_review_result,
    run_reviewer_for_dp,
    upsert_config,
)
from pointlessql.services.data_products.activity import (
    ActivityRow,
    fetch_activity_for_dp,
)
from pointlessql.services.data_products.badges import (
    compute_badges_bulk,
    compute_badges_for_dp,
)
from pointlessql.services.data_products.cooccurrence import (
    fetch_recommendations_for_user,
    fetch_related,
    refresh_cooccurrence,
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
    "ReviewVerdict",
    "build_draft_yaml",
    "build_prompt",
    "candidate_row_count",
    "compute_badges_bulk",
    "compute_badges_for_dp",
    "fetch_activity_for_dp",
    "fetch_recommendations_for_user",
    "fetch_related",
    "fetch_trending",
    "iter_opted_in_dp_ids",
    "parse_review_result",
    "refresh_cooccurrence",
    "refresh_passport_for_dp",
    "refresh_stale_passports",
    "refresh_trending",
    "render_passport",
    "run_reviewer_for_dp",
    "scan_candidates",
    "upsert_config",
]
