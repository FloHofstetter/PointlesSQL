"""Forward-propagate pin schemas through a canvas DAG.

The compiler in :mod:`pointlessql.services.canvas_df._compiler` calls
``infer_block`` once per node as part of producing the SQL fragment;
this module re-runs the inference pass *standalone* so the editor can
ask "what's the schema at every pin?" without paying for a full
compile.

Returns a dict keyed by ``(node_id, pin_name)`` with the
:class:`PinSchema` flowing through that pin.  Errors land in a
parallel list — :class:`CompileError` envelopes the editor can render
as red wires + validation badges next to the offending pin.
"""

from __future__ import annotations

from pointlessql.services.canvas_core import topo_sort
from pointlessql.services.canvas_df._blocks import BLOCK_REGISTRY, infer_block
from pointlessql.services.canvas_df._types import (
    CanvasDoc,
    CompileError,
    PinSchema,
)


def validate_schema_flow(
    doc: CanvasDoc,
    *,
    seed_schemas: dict[str, PinSchema] | None = None,
) -> tuple[dict[tuple[str, str], PinSchema], list[CompileError]]:
    """Propagate pin schemas through *doc* and surface mismatches.

    Args:
        doc: The canvas document under inspection.
        seed_schemas: ``{input_port_node_id: PinSchema}`` populated by
            the caller from the live UC schema for each InputPort.
            Pass ``None`` to skip seeding — every InputPort then ends
            up with an ``unknown=True`` schema (still useful for
            envelope validation).

    Returns:
        ``(per_pin_schemas, errors)``.  ``per_pin_schemas`` maps
        ``(node_id, pin_name)`` for every input and output pin in the
        graph.  Output pins always carry the inferred schema; input
        pins inherit the upstream output schema when wired.
    """
    errors: list[CompileError] = []
    if not doc.nodes:
        errors.append(CompileError(kind="empty_doc", message="Canvas is empty."))
        return {}, errors

    for node in doc.nodes:
        if node.block_type not in BLOCK_REGISTRY:
            errors.append(
                CompileError(
                    kind="unknown_block",
                    node_id=node.id,
                    message=f"Unknown block_type {node.block_type!r}.",
                )
            )
    if errors:
        return {}, errors

    ordered = topo_sort(list(doc.nodes), list(doc.edges), errors)
    if ordered is None:
        return {}, errors

    edges_in: dict[tuple[str, str], tuple[str, str]] = {}
    for edge in doc.edges:
        edges_in[(edge.target_node_id, edge.target_pin)] = (
            edge.source_node_id,
            edge.source_pin,
        )

    seeds = seed_schemas or {}
    output_schemas: dict[str, PinSchema] = {}
    per_pin: dict[tuple[str, str], PinSchema] = {}

    for node in ordered:
        spec = BLOCK_REGISTRY[node.block_type]
        input_schemas: dict[str, PinSchema] = {}
        for pin_name, _pin_kind in spec.input_pins:
            wired = edges_in.get((node.id, pin_name))
            if wired is None:
                continue
            src_node_id, _src_pin = wired
            schema = output_schemas.get(src_node_id)
            if schema is not None:
                input_schemas[pin_name] = schema
                per_pin[(node.id, pin_name)] = schema

        inferred = infer_block(
            block_type=node.block_type,
            node_id=node.id,
            input_schemas=input_schemas,
            cfg=node.config,
            errors=errors,
            seed=seeds.get(node.id),
        )
        output_schemas[node.id] = inferred
        for pin_name, _pin_kind in spec.output_pins:
            per_pin[(node.id, pin_name)] = inferred

    return per_pin, errors


__all__ = ["validate_schema_flow"]
