"""Reusable dataframe canvas layer: typed blocks → DuckDB SQL.

Sits between the consumer-agnostic graph kernel
(:mod:`pointlessql.services.canvas_core`) and the concrete consumers.  It
owns everything about turning a :class:`CanvasDoc` of typed dataframe
blocks into a DuckDB ``WITH … SELECT …`` CTE chain plus its schema-flow
analysis — and nothing about *where* the result is read from or written
to.  That deliberate ignorance is what lets multiple surfaces reuse it: a
data product materialises the compiled SQL into a Delta table, while a
notebook builder hands the same SQL back as a query.

This layer imports only :mod:`canvas_core` (and DuckDB for the ``SQL``
block's ``DESCRIBE`` round-trip).  It never imports soyuz, settings, or
any storage backend — that coupling lives one tier up in each consumer.
"""

from pointlessql.services.canvas_df._blocks import (
    BLOCK_REGISTRY,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
    compile_block,
    infer_block,
    register_block,
)
from pointlessql.services.canvas_df._compiler import (
    CompiledSelect,
    compile_canvas,
    compile_to_select,
    render_sql,
)
from pointlessql.services.canvas_df._edge_types import (
    EdgeCategory,
    categorize_columns,
    categorize_pin_schema,
)
from pointlessql.services.canvas_df._schema_flow import validate_schema_flow
from pointlessql.services.canvas_df._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    ColumnSpec,
    CompileError,
    PinSchema,
    SinkSpec,
    SQLFragment,
)

__all__ = [
    "BLOCK_REGISTRY",
    "OUTPUT_MODES",
    "BlockSpec",
    "CanvasDoc",
    "CanvasEdge",
    "CanvasNode",
    "ColumnSpec",
    "CompileError",
    "CompiledBlock",
    "CompiledSelect",
    "EdgeCategory",
    "PinSchema",
    "SQLFragment",
    "SinkSpec",
    "categorize_columns",
    "categorize_pin_schema",
    "compile_block",
    "compile_canvas",
    "compile_to_select",
    "infer_block",
    "register_block",
    "render_sql",
    "validate_schema_flow",
]
