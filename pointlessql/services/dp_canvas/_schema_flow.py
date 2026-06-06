"""Back-compat shim: schema-flow analysis now lives in :mod:`canvas_df`.

The forward pin-schema propagation is consumer-agnostic and moved to
:mod:`pointlessql.services.canvas_df._schema_flow`.  This module re-exports
:func:`validate_schema_flow` so existing
``from pointlessql.services.dp_canvas._schema_flow import …`` callers keep
resolving unchanged.
"""

from __future__ import annotations

from pointlessql.services.canvas_df._schema_flow import validate_schema_flow

__all__ = ["validate_schema_flow"]
