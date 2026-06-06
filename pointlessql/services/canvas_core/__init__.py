"""Consumer-agnostic graph kernel shared by every canvas surface.

This is the bottom tier of the canvas stack: the document envelope
(:class:`CanvasDoc` / :class:`CanvasNode` / :class:`CanvasEdge`), the
deterministic topological sort, structural envelope validation, the
structural diff, and a domain-agnostic node-kind registry.  It depends on
nothing project-local — every other canvas layer (``canvas_df`` for
dataframe pipelines, the data-product / scheduler / notebook consumers)
builds on it without it ever knowing they exist.
"""

from pointlessql.services.canvas_core._diff import (
    CanvasDiff,
    CanvasEdgeDiff,
    CanvasNodeDiff,
    diff_docs,
)
from pointlessql.services.canvas_core._graph import topo_sort
from pointlessql.services.canvas_core._registry import (
    NodeKindRegistry,
    NodeKindSpec,
)
from pointlessql.services.canvas_core._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
)
from pointlessql.services.canvas_core._validate import validate_envelope

__all__ = [
    "CanvasDiff",
    "CanvasDoc",
    "CanvasEdge",
    "CanvasEdgeDiff",
    "CanvasNode",
    "CanvasNodeDiff",
    "CompileError",
    "NodeKindRegistry",
    "NodeKindSpec",
    "diff_docs",
    "topo_sort",
    "validate_envelope",
]
