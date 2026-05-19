"""Column-statistics computation for the chat NL→SQL describe tool.

The Phase 91 ``pql_describe_columns_with_stats`` plugin tool calls
``GET /api/catalogs/{c}/schemas/{s}/tables/{t}/stats`` to learn what
a table looks like before drafting SQL.  This package owns the
read-side pandas reduction; the route layer in
``pointlessql.api.catalog_routes`` does the auth gate + the
async-to-thread bridge.
"""

from __future__ import annotations

from pointlessql.services.column_stats._compute import (
    STATS_CACHE_TTL_SECONDS,
    compute_table_stats,
    invalidate_table_stats,
)

__all__ = [
    "STATS_CACHE_TTL_SECONDS",
    "compute_table_stats",
    "invalidate_table_stats",
]
