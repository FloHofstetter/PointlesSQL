# pyright: reportUnusedImport=false
"""Reusable dataframe block-type registry.

:mod:`._base` holds the shared dataclasses, the ``BLOCK_REGISTRY``, and the
public :func:`compile_block` / :func:`infer_block` entry points.  Each
block's pure ``_compile_*`` / ``_infer_*`` helpers live in a per-category
sibling module (``_relational`` / ``_reshape`` / ``_columns`` / ``_sql``)
that calls :func:`._base.register_block` to add its types — pins plus the
two functions — to the registry at import time.  Importing those modules
here is what wires the registry.

These four categories are the *consumer-agnostic* transforms — they read
and reshape rowsets without knowing where the data comes from or goes.
Source and sink blocks (read a Unity Catalog table, write a Delta table)
are domain-specific and register themselves from their owning consumer
(e.g. the data-product canvas adds ``InputPort`` / ``OutputPort`` from its
own block package) into this same shared registry.
"""

from __future__ import annotations

# Imported for the registration side effects (each module populates the
# dispatch tables on import); base must be imported first, above.
from pointlessql.services.canvas_df._blocks import (  # noqa: E402
    _columns,  # noqa: F401
    _relational,  # noqa: F401
    _reshape,  # noqa: F401
    _sql,  # noqa: F401
)
from pointlessql.services.canvas_df._blocks._base import (
    BLOCK_REGISTRY,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
    compile_block,
    infer_block,
    register_block,
)

__all__ = [
    "BLOCK_REGISTRY",
    "OUTPUT_MODES",
    "BlockSpec",
    "CompiledBlock",
    "compile_block",
    "infer_block",
    "register_block",
]
