# pyright: reportUnusedImport=false
"""Data-product block catalog: the shared dataframe blocks plus DP sources/sinks.

The consumer-agnostic transform blocks (``Filter`` / ``Join`` / ``GroupBy``
/ raw ``SQL`` …) and the registry machinery itself live in the reusable
:mod:`pointlessql.services.canvas_df._blocks` layer; importing that package
both wires those transforms into the shared ``BLOCK_REGISTRY`` and gives us
the public :func:`compile_block` / :func:`infer_block` entry points to
re-export.

This package adds the *data-product-specific* blocks on top: ``InputPort``
/ ``DataProduct`` sources that read a Unity Catalog table, and the
``OutputPort`` / ``FileOutput`` / ``FileInput`` blocks that bridge Delta and
the local file sandbox.  Their ``_io`` / ``_files`` modules call
:func:`register_block` at import time, adding their types to the *same*
shared registry, so a compile sees every block a data-product canvas can
contain.  The public import surface is unchanged for existing callers.
"""

from __future__ import annotations

# Importing the dataframe layer wires the shared transform blocks into
# BLOCK_REGISTRY and exposes the registry machinery we re-export below.
from pointlessql.services.canvas_df._blocks import (
    BLOCK_REGISTRY,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
    compile_block,
    infer_block,
)

# Imported for the registration side effects — each module adds its
# data-product-specific block types to the shared registry on import.
from pointlessql.services.dp_canvas._blocks import (  # noqa: E402
    _files,  # noqa: F401
    _io,  # noqa: F401
)

__all__ = [
    "BLOCK_REGISTRY",
    "OUTPUT_MODES",
    "BlockSpec",
    "CompiledBlock",
    "compile_block",
    "infer_block",
]
