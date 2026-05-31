"""Compile a :class:`CanvasDoc` to a DuckDB :class:`SQLFragment`.

Pattern reference (not reused — different shape): the linear-only
``compile_nodes`` in :mod:`pointlessql.services.canvas._compiler`.
That sibling translates an *ordered list* into a PQL script; this
one translates a *DAG* into a ``WITH … SELECT …`` CTE chain DuckDB
runs natively.

Topological sort uses Kahn's algorithm so a cycle surfaces as a
structured :class:`CompileError` instead of an infinite loop.  CTE
names are deterministic (``n{topo_index}_{block_type_lower}``) so
diffs between graph versions stay readable for any downstream
diff view.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from pointlessql.services.dp_canvas._blocks import (
    BLOCK_REGISTRY,
    compile_block,
    infer_block,
)
from pointlessql.services.dp_canvas._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
    PinSchema,
    SQLFragment,
)

_BASE_TABLE_RE = re.compile(
    r'(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)


def _cte_name(idx: int, block_type: str) -> str:
    return f"n{idx}_{block_type.lower()}"


def _validate_envelope(doc: CanvasDoc, errors: list[CompileError]) -> bool:
    """Surface envelope problems before topo-sort.

    Returns True when the document is well-formed enough for topo-sort
    to proceed; any envelope error blocks compilation early.
    """
    if not doc.nodes:
        errors.append(CompileError(kind="empty_doc", message="Canvas is empty."))
        return False
    seen: set[str] = set()
    for node in doc.nodes:
        if node.id in seen:
            errors.append(
                CompileError(
                    kind="duplicate_node_id",
                    node_id=node.id,
                    message=f"Duplicate node id {node.id!r}.",
                )
            )
        seen.add(node.id)
    node_ids = {n.id for n in doc.nodes}
    edge_ids: set[str] = set()
    for edge in doc.edges:
        if edge.id in edge_ids:
            errors.append(
                CompileError(
                    kind="duplicate_node_id",
                    node_id=edge.id,
                    message=f"Duplicate edge id {edge.id!r}.",
                )
            )
        edge_ids.add(edge.id)
        if edge.source_node_id not in node_ids:
            errors.append(
                CompileError(
                    kind="edge_target_missing",
                    node_id=edge.source_node_id,
                    pin=edge.source_pin,
                    message=f"Edge {edge.id!r} source node {edge.source_node_id!r} missing.",
                )
            )
        if edge.target_node_id not in node_ids:
            errors.append(
                CompileError(
                    kind="edge_target_missing",
                    node_id=edge.target_node_id,
                    pin=edge.target_pin,
                    message=f"Edge {edge.id!r} target node {edge.target_node_id!r} missing.",
                )
            )
        if edge.source_node_id == edge.target_node_id:
            errors.append(
                CompileError(
                    kind="cycle",
                    node_id=edge.source_node_id,
                    message=f"Edge {edge.id!r} forms a self-loop on {edge.source_node_id!r}.",
                )
            )
    return not errors


def _topo_sort(
    nodes: list[CanvasNode], edges: list[CanvasEdge], errors: list[CompileError]
) -> list[CanvasNode] | None:
    """Kahn's algorithm, returning ``None`` and recording an error on cycle."""
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        incoming[edge.target_node_id].add(edge.source_node_id)
        outgoing[edge.source_node_id].add(edge.target_node_id)
    by_id = {n.id: n for n in nodes}
    ready = sorted([n.id for n in nodes if not incoming.get(n.id)])
    ordered: list[str] = []
    while ready:
        nid = ready.pop(0)
        ordered.append(nid)
        for downstream in sorted(outgoing.get(nid, set())):
            incoming[downstream].discard(nid)
            if not incoming[downstream]:
                ready.append(downstream)
                ready.sort()
    if len(ordered) != len(nodes):
        remaining = sorted({n.id for n in nodes} - set(ordered))
        errors.append(
            CompileError(
                kind="cycle",
                node_id=remaining[0] if remaining else None,
                message=f"Canvas contains a cycle involving nodes {remaining!r}.",
            )
        )
        return None
    return [by_id[nid] for nid in ordered]


def _check_block_types(nodes: Iterable[CanvasNode], errors: list[CompileError]) -> None:
    for node in nodes:
        if node.block_type not in BLOCK_REGISTRY:
            errors.append(
                CompileError(
                    kind="unknown_block",
                    node_id=node.id,
                    message=f"Unknown block_type {node.block_type!r}.",
                )
            )


def _check_output_port_count(
    nodes: Iterable[CanvasNode], errors: list[CompileError]
) -> CanvasNode | None:
    outputs = [n for n in nodes if n.block_type == "OutputPort"]
    if not outputs:
        errors.append(
            CompileError(
                kind="output_port_count",
                message="Canvas must contain exactly one OutputPort block.",
            )
        )
        return None
    if len(outputs) > 1:
        errors.append(
            CompileError(
                kind="output_port_count",
                node_id=outputs[1].id,
                message=("Canvas has multiple OutputPort blocks; v1 supports exactly one."),
            )
        )
        return None
    return outputs[0]


def _extract_base_tables(sql: str) -> list[str]:
    return _BASE_TABLE_RE.findall(sql)


def compile_canvas(
    doc: CanvasDoc,
    *,
    upstream_schemas: dict[str, PinSchema] | None = None,
) -> tuple[SQLFragment | None, list[CompileError]]:
    """Compile *doc* to a CTE-chain :class:`SQLFragment`.

    Args:
        doc: The canvas document to compile.
        upstream_schemas: Optional ``{input_port_node_id: PinSchema}``
            seeding so the InputPort blocks know what their output
            shape is.  The executor passes a fully-resolved map after
            asking soyuz for the schema of every ``table_fqn``; tests
            may seed by hand.

    Returns:
        ``(fragment, [])`` on success, ``(None, [errors])`` on
        failure.  ``errors`` is a *list*, never raised — the editor
        wants to render every problem at once.
    """
    errors: list[CompileError] = []
    if not _validate_envelope(doc, errors):
        return None, errors
    _check_block_types(doc.nodes, errors)
    if errors:
        return None, errors
    output_node = _check_output_port_count(doc.nodes, errors)
    if output_node is None:
        return None, errors

    ordered_nodes = _topo_sort(list(doc.nodes), list(doc.edges), errors)
    if ordered_nodes is None:
        return None, errors

    # Index edges by (target_node_id, target_pin) so each block can look
    # up which upstream CTE feeds each of its input pins.
    edges_in: dict[tuple[str, str], tuple[str, str]] = {}
    for edge in doc.edges:
        edges_in[(edge.target_node_id, edge.target_pin)] = (
            edge.source_node_id,
            edge.source_pin,
        )

    seeds = upstream_schemas or {}
    cte_names: dict[str, str] = {}
    output_schemas: dict[str, PinSchema] = {}
    ctes: list[tuple[str, str]] = []

    for idx, node in enumerate(ordered_nodes):
        spec = BLOCK_REGISTRY[node.block_type]
        input_ctes: dict[str, str] = {}
        input_schemas: dict[str, PinSchema] = {}
        for pin_name, _pin_kind in spec.input_pins:
            wired = edges_in.get((node.id, pin_name))
            if wired is None:
                continue
            src_node_id, _src_pin = wired
            src_cte = cte_names.get(src_node_id)
            if src_cte is not None:
                input_ctes[pin_name] = src_cte
            src_schema = output_schemas.get(src_node_id)
            if src_schema is not None:
                input_schemas[pin_name] = src_schema

        inferred = infer_block(
            block_type=node.block_type,
            node_id=node.id,
            input_schemas=input_schemas,
            cfg=node.config,
            errors=errors,
            seed=seeds.get(node.id),
        )
        compiled = compile_block(
            block_type=node.block_type,
            node_id=node.id,
            inputs=input_ctes,
            output_schema=inferred,
            cfg=node.config,
            errors=errors,
        )
        if compiled is None:
            continue
        name = _cte_name(idx, node.block_type)
        cte_names[node.id] = name
        output_schemas[node.id] = inferred
        ctes.append((name, compiled.sql))

    if errors:
        return None, errors

    final_cte = cte_names.get(output_node.id)
    if final_cte is None:
        errors.append(
            CompileError(
                kind="bad_config",
                node_id=output_node.id,
                message="OutputPort failed to compile — no CTE recorded.",
            )
        )
        return None, errors

    base_tables: list[str] = []
    seen_tables: set[str] = set()
    for _name, sql in ctes:
        for fqn in _extract_base_tables(sql):
            if fqn in seen_tables:
                continue
            seen_tables.add(fqn)
            base_tables.append(fqn)

    fragment = SQLFragment(
        ctes=ctes,
        final_cte=final_cte,
        referenced_tables=base_tables,
        output_schema=output_schemas[output_node.id],
    )
    return fragment, []


def render_sql(fragment: SQLFragment) -> str:
    """Render *fragment* as a single DuckDB-executable ``WITH … SELECT …`` string."""
    if not fragment.ctes:
        return f"SELECT * FROM {fragment.final_cte}"
    cte_clauses = ",\n".join(f"{name} AS (\n{body}\n)" for name, body in fragment.ctes)
    return f"WITH {cte_clauses}\nSELECT * FROM {fragment.final_cte}"


__all__ = ["compile_canvas", "render_sql"]
