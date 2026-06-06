"""Re-export shim for the shared canvas structural diff.

The diff types and :func:`diff_docs` moved to the consumer-agnostic
:mod:`pointlessql.services.canvas_core` kernel.  This shim keeps the
historical ``pointlessql.services.dp_canvas._diff`` import path working
for the data-product canvas routes that import it directly.
"""

from __future__ import annotations

from pointlessql.services.canvas_core._diff import (
    CanvasDiff,
    CanvasEdgeDiff,
    CanvasNodeDiff,
    diff_docs,
)

__all__ = ["CanvasDiff", "CanvasEdgeDiff", "CanvasNodeDiff", "diff_docs"]
