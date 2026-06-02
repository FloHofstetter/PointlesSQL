"""Visual Data Product canvas: block-graph → DuckDB SQL → Delta.

Service-layer surface for the visual block-and-wire editor that
authors data products without notebook or raw-SQL code.  A canvas is
a DAG of typed blocks (``InputPort`` / ``Filter`` / ``Join`` /
``GroupBy`` / ``OutputPort`` …) — the compiler turns it into a
``WITH … SELECT …`` CTE chain DuckDB executes natively, and the
executor materialises the result into a Delta table the parent data
product publishes through a registered output port.

HTTP routes + Rete.js frontend live in sibling layers; this
package stays pure service-side so the editor frontend can be
swapped without touching compile/materialise semantics.
"""

from pointlessql.services.dp_canvas._blocks import (
    BLOCK_REGISTRY,
    OUTPUT_MODES,
    BlockSpec,
    CompiledBlock,
)
from pointlessql.services.dp_canvas._compiler import compile_canvas, render_sql
from pointlessql.services.dp_canvas._executor import execute_canvas
from pointlessql.services.dp_canvas._schema_flow import validate_schema_flow
from pointlessql.services.dp_canvas._storage import load_latest_graph, save_graph
from pointlessql.services.dp_canvas._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    ColumnSpec,
    CompileError,
    MultiExecuteResult,
    PinSchema,
    SinkResult,
    SinkSpec,
    SQLFragment,
)
from pointlessql.services.dp_canvas._uc_lookup import (
    fetch_table_info,
    resolve_storage_location,
    resolve_table_schema,
    table_info_to_pin_schema,
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
    "MultiExecuteResult",
    "PinSchema",
    "SQLFragment",
    "SinkResult",
    "SinkSpec",
    "compile_canvas",
    "execute_canvas",
    "fetch_table_info",
    "load_latest_graph",
    "render_sql",
    "resolve_storage_location",
    "resolve_table_schema",
    "save_graph",
    "table_info_to_pin_schema",
    "validate_schema_flow",
]
