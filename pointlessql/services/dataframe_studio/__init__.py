"""DataFrame Studio — a sink-free visual query builder over ``canvas_df``.

The Studio reuses the shared dataframe blocks to compile a pipeline to a
governed ``SELECT`` (via :func:`canvas_df.compile_to_select`), preview it,
and hand the SQL back to a notebook cell.  It is read-only: there is **no**
UC materialise, **no** version ledger, and **no** sink blocks — the graph
terminal is "the node you point at".

This package is the thin consumer logic (the disallowed-block guard +
compile wrapper); the HTTP adapters live in
:mod:`pointlessql.api.dataframe_studio_routes` and reuse the data-product
canvas helpers (soyuz client, schema seeding, ``preview_until``).
"""

from __future__ import annotations

from pointlessql.services.dataframe_studio._studio import (
    DISALLOWED_BLOCKS,
    compile_studio_select,
    disallowed_block_errors,
)

__all__ = [
    "DISALLOWED_BLOCKS",
    "compile_studio_select",
    "disallowed_block_errors",
]
