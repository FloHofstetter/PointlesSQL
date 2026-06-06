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
from collections.abc import Iterable

from pointlessql.services.canvas_core import topo_sort
from pointlessql.services.canvas_core._validate import (
    validate_envelope as _validate_envelope,
)
from pointlessql.services.dp_canvas._blocks import (
    BLOCK_REGISTRY,
    compile_block,
    infer_block,
)
from pointlessql.services.dp_canvas._types import (
    CanvasDoc,
    CanvasNode,
    CompileError,
    PinSchema,
    SinkSpec,
    SQLFragment,
)

_BASE_TABLE_RE = re.compile(
    r'(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)"?',
    re.IGNORECASE,
)


def _cte_name(idx: int, block_type: str) -> str:
    return f"n{idx}_{block_type.lower()}"


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


def _collect_output_nodes(
    nodes: Iterable[CanvasNode], errors: list[CompileError]
) -> list[CanvasNode]:
    """Return every sink node (OutputPort or FileOutput); error when none exist.

    A canvas may publish several sinks — a Delta table per OutputPort or a
    file per FileOutput — so the only hard requirement here is that at least
    one sink exists.  Per-sink config validity (port name, target FQN, mode,
    path) is checked downstream by each block's own ``compile_block``;
    cross-sink collisions (duplicate target / port name) are caught in
    :func:`compile_canvas`.
    """
    outputs = [n for n in nodes if n.block_type in ("OutputPort", "FileOutput")]
    if not outputs:
        errors.append(
            CompileError(
                kind="output_port_count",
                message="Canvas must contain at least one output (OutputPort or FileOutput).",
            )
        )
    return outputs


def _merge_on_from_config(cfg: dict[str, object]) -> list[str]:
    raw = cfg.get("merge_on")
    if not isinstance(raw, list):
        return []
    return [str(c).strip() for c in raw if str(c).strip()]


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
    output_nodes = _collect_output_nodes(doc.nodes, errors)
    if not output_nodes:
        return None, errors

    ordered_nodes = topo_sort(list(doc.nodes), list(doc.edges), errors)
    if ordered_nodes is None:
        return None, errors

    # Index edges by (target_node_id, target_pin) so each block can look
    # up which upstream CTE feeds each of its input pins.  An input pin
    # accepts exactly one connection — two edges landing on the same pin
    # would silently overwrite here (last-edge-wins), so flag it instead
    # of quietly dropping a wire.
    edges_in: dict[tuple[str, str], tuple[str, str]] = {}
    for edge in doc.edges:
        key = (edge.target_node_id, edge.target_pin)
        if key in edges_in:
            errors.append(
                CompileError(
                    kind="duplicate_pin",
                    node_id=edge.target_node_id,
                    pin=edge.target_pin,
                    message=(
                        f"Input pin {edge.target_pin!r} on node "
                        f"{edge.target_node_id!r} is wired by more than one edge; "
                        "an input pin accepts a single connection."
                    ),
                )
            )
            continue
        edges_in[key] = (edge.source_node_id, edge.source_pin)
    if errors:
        return None, errors

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

    sinks: list[SinkSpec] = []
    seen_targets: dict[str, str] = {}
    seen_port_names: dict[str, str] = {}
    for output_node in output_nodes:
        final_cte = cte_names.get(output_node.id)
        if final_cte is None:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=output_node.id,
                    message="Sink block failed to compile — no CTE recorded.",
                )
            )
            continue
        cfg = output_node.config
        if output_node.block_type == "FileOutput":
            rel = str(cfg.get("path") or "").strip()
            if rel in seen_targets:
                errors.append(
                    CompileError(
                        kind="duplicate_sink",
                        node_id=output_node.id,
                        message=(
                            f"Two FileOutput blocks write the same path {rel!r}; "
                            "each sink needs a distinct path."
                        ),
                    )
                )
                continue
            seen_targets[rel] = output_node.id
            sinks.append(
                SinkSpec(
                    output_node_id=output_node.id,
                    # File sinks have no UC port; the file name keeps the
                    # per-sink label short and human-readable.
                    port_name=(rel.rsplit("/", 1)[-1] or output_node.id),
                    target_fqn=rel,
                    mode="overwrite",
                    final_cte=final_cte,
                    output_schema=output_schemas[output_node.id],
                    sink_kind="file",
                    file_path=rel,
                    file_format=str(cfg.get("format") or "parquet").strip().lower(),
                )
            )
            continue
        port_name = str(cfg.get("port_name") or "").strip()
        target_fqn = str(cfg.get("materialized_table") or "").strip()
        if target_fqn in seen_targets:
            errors.append(
                CompileError(
                    kind="duplicate_sink",
                    node_id=output_node.id,
                    message=(
                        f"Two OutputPort blocks write the same target table "
                        f"{target_fqn!r}; each sink needs a distinct table."
                    ),
                )
            )
            continue
        if port_name in seen_port_names:
            errors.append(
                CompileError(
                    kind="duplicate_sink",
                    node_id=output_node.id,
                    message=(
                        f"Two OutputPort blocks share the port name {port_name!r}; "
                        "each output port needs a distinct name."
                    ),
                )
            )
            continue
        seen_targets[target_fqn] = output_node.id
        seen_port_names[port_name] = output_node.id
        sinks.append(
            SinkSpec(
                output_node_id=output_node.id,
                port_name=port_name,
                target_fqn=target_fqn,
                mode=str(cfg.get("mode") or "overwrite").strip().lower(),
                merge_on=_merge_on_from_config(cfg),
                final_cte=final_cte,
                output_schema=output_schemas[output_node.id],
            )
        )

    if errors:
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
        sinks=sinks,
        referenced_tables=base_tables,
    )
    return fragment, []


def render_sql(fragment: SQLFragment, sink: SinkSpec) -> str:
    """Render one *sink* of *fragment* as a DuckDB ``WITH … SELECT …`` string.

    Every sink shares *fragment*'s CTE chain; only the terminal
    ``SELECT * FROM <final_cte>`` differs.  The executor calls this once
    per sink against the same DuckDB connection.
    """
    if not fragment.ctes:
        return f"SELECT * FROM {sink.final_cte}"
    cte_clauses = ",\n".join(f"{name} AS (\n{body}\n)" for name, body in fragment.ctes)
    return f"WITH {cte_clauses}\nSELECT * FROM {sink.final_cte}"


__all__ = ["compile_canvas", "render_sql"]
