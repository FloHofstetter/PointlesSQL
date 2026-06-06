"""DataFrame Studio consumer logic over the shared ``canvas_df`` core.

Two small responsibilities the HTTP layer leans on:

* reject the blocks the Studio does not allow — sinks (``OutputPort`` /
  ``FileOutput``) and the data-product drill-in source (``DataProduct``).
  The Studio never materialises and is not data-product-scoped, so those
  blocks have no meaning here; flagging them keeps the editor honest.
* compile a slice of the canvas to a governed ``SELECT`` ending at a chosen
  terminal node, guarding the disallowed blocks first.

Everything else (running the SELECT, schema-flow validation) is the shared
``canvas_df`` / ``preview_until`` machinery the data-product canvas already
uses; the Studio is deliberately thin.
"""

from __future__ import annotations

from pointlessql.services.canvas_df import (
    CanvasDoc,
    CompiledSelect,
    CompileError,
    PinSchema,
    compile_to_select,
)

# Blocks with no meaning in the sink-free, materialise-free Studio.
DISALLOWED_BLOCKS = frozenset({"OutputPort", "FileOutput", "DataProduct"})


def disallowed_block_errors(doc: CanvasDoc) -> list[CompileError]:
    """Return a ``bad_config`` error for each sink / DP block in *doc*."""
    errors: list[CompileError] = []
    for node in doc.nodes:
        if node.block_type in DISALLOWED_BLOCKS:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node.id,
                    message=(
                        f"block {node.block_type!r} is not available in DataFrame "
                        "Studio — it has no sink or materialise step; emit the SQL "
                        "to a notebook instead."
                    ),
                )
            )
    return errors


def compile_studio_select(
    doc: CanvasDoc,
    *,
    terminal_node_id: str,
    upstream_schemas: dict[str, PinSchema] | None = None,
) -> tuple[CompiledSelect | None, list[CompileError]]:
    """Compile *doc* to a SELECT ending at *terminal_node_id*, guarding sinks.

    Args:
        doc: The Studio canvas document.
        terminal_node_id: The node whose output the SELECT emits.
        upstream_schemas: Optional source-block schema seeds.

    Returns:
        ``(CompiledSelect, [])`` on success; ``(None, [errors])`` when the
        doc contains a disallowed block or fails to compile.
    """
    blocked = disallowed_block_errors(doc)
    if blocked:
        return None, blocked
    return compile_to_select(
        doc, terminal_node_id=terminal_node_id, upstream_schemas=upstream_schemas
    )
