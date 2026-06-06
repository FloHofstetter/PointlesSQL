"""Back-compat shim: the canvas compiler now lives in :mod:`canvas_df`.

The DAG-to-DuckDB compiler is consumer-agnostic and moved to
:mod:`pointlessql.services.canvas_df._compiler` so the notebook builder can
reuse it without dragging in any data-product coupling.  This module
re-exports its public surface so existing
``from pointlessql.services.dp_canvas._compiler import …`` callers (the
executor and the per-node preview) keep resolving unchanged.
"""

from __future__ import annotations

from pointlessql.services.canvas_df._compiler import compile_canvas, render_sql

__all__ = ["compile_canvas", "render_sql"]
