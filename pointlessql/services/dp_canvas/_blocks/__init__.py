# pyright: reportUnusedImport=false
"""Block-type registry for the visual data-product canvas.

The registry was a single 1.5k-line module; it is now a package whose
:mod:`._base` holds the shared dataclasses, the ``BLOCK_REGISTRY``, and
the public :func:`compile_block` / :func:`infer_block` entry points.
Each block's pure ``_compile_*`` / ``_infer_*`` helpers live in a
per-category sibling module (``_io`` / ``_relational`` / ``_reshape`` /
``_columns`` / ``_sql``) that calls :func:`._base.register_block` to add
its types — pins plus the two functions — to the registry at import
time.  Importing those modules here is what wires the registry, so the
public import surface is unchanged for callers.
"""

from __future__ import annotations

# Imported for the registration side effects (each module populates the
# dispatch tables on import); base must be imported first, above.
from pointlessql.services.dp_canvas._blocks import (  # noqa: E402
    _columns,  # noqa: F401
    _io,  # noqa: F401
    _relational,  # noqa: F401
    _reshape,  # noqa: F401
    _sql,  # noqa: F401
)
from pointlessql.services.dp_canvas._blocks._base import (
    BLOCK_REGISTRY,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
    compile_block,
    infer_block,
)

__all__ = [
    "BLOCK_REGISTRY",
    "OUTPUT_MODES",
    "BlockSpec",
    "CompiledBlock",
    "compile_block",
    "infer_block",
]