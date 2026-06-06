"""Re-export shim for the shared graph ordering primitive.

``topo_sort`` moved to the consumer-agnostic
:mod:`pointlessql.services.canvas_core` kernel.  This shim keeps the
historical ``pointlessql.services.dp_canvas._graph`` import path working
for the compiler, the schema-flow validator, and any test that reaches
for it directly.
"""

from __future__ import annotations

from pointlessql.services.canvas_core._graph import topo_sort

__all__ = ["topo_sort"]
