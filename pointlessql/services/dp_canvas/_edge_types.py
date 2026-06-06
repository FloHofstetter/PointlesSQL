"""Back-compat shim: edge-type categorisation now lives in :mod:`canvas_df`.

The pin-schema → edge-category bucketing is consumer-agnostic and moved to
:mod:`pointlessql.services.canvas_df._edge_types`.  This module re-exports
its public surface so existing
``from pointlessql.services.dp_canvas._edge_types import …`` callers (the
validate route, tests) keep resolving unchanged.
"""

from __future__ import annotations

from pointlessql.services.canvas_df._edge_types import (
    EdgeCategory,
    categorize_columns,
    categorize_pin_schema,
)

__all__ = ["categorize_columns", "categorize_pin_schema", "EdgeCategory"]
