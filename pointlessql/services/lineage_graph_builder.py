"""run-scoped lineage DAG builder.

Joins :class:`pointlessql.models.LineageRowEdge` and
:class:`pointlessql.models.LineageColumnMap` for one ``run_id`` (and
optional ``op_id`` filter) into a single graph payload that the
new run-detail Graph sub-tab feeds straight into cytoscape.js.

The shape is deliberately flat — node + edge dicts with primitive
fields — so the frontend never has to touch ORM objects and so the
`pql_query_run_graph` Hermes tool can ship the same payload
unchanged in a future sprint.

One node per **distinct table** seen in either table.  One edge per
**(source_table, target_table, op_id)** triple, with the per-edge
``transform_kinds`` aggregated from the column-map and the
``column_pairs`` list emitted in row order so the click-a-column
highlight on the frontend is deterministic.

The empty-payload case (no row-edges and no column-map for the run
or op) returns ``{"nodes": [], "edges": [], …}`` so the frontend
can render a clean empty-state instead of having to special-case
the absence of either table.
"""
from __future__ import annotations

from typing import Any, cast

from fastapi import Request
from sqlalchemy import select

from pointlessql.models import (
    AgentRunOperation,
    LineageColumnMap,
    LineageRowEdge,
)


def build_lineage_graph(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> dict[str, Any]:
    """Build a `{nodes, edges}` graph payload for one run.

    Args:
        request: Incoming FastAPI request — for the SQLAlchemy
            session factory.
        run_id: Owning :class:`pointlessql.models.AgentRun.id`.
        op_id: Optional :class:`AgentRunOperation.id` filter — when
            set, the graph contains only the edges + nodes touched
            by that single op.  Useful for op-scoped drill-down
            from the run-detail Operations tab.

    Returns:
        Dict shaped::

            {
                "run_id": "<uuid>",
                "op_id": int | None,
                "nodes": [
                    {"id": "<fqn>", "table": "<fqn>", "columns": [...]},
                    ...
                ],
                "edges": [
                    {
                        "id": "<source>__<target>__<op_id>",
                        "source": "<fqn>",
                        "target": "<fqn>",
                        "op_id": int,
                        "op_ordinal": int,
                        "op_name": str,
                        "transform_kinds": [str, ...],
                        "column_pairs": [
                            {
                                "source_column": str | None,
                                "target_column": str,
                                "transform_kind": str,
                            },
                            ...
                        ],
                        "row_edge_count": int,
                    },
                    ...
                ],
            }
    """
    factory = request.app.state.session_factory

    nodes_by_fqn: dict[str, dict[str, Any]] = {}
    # Edges are keyed on (source, target, op_id) so identity tells us
    # whether we have already seen this triple.
    edges_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    op_meta: dict[int, tuple[int, str]] = {}  # op_id → (ordinal, op_name)

    def _ensure_node(fqn: str) -> None:
        if fqn and fqn not in nodes_by_fqn:
            nodes_by_fqn[fqn] = {
                "id": fqn,
                "table": fqn,
                "columns": [],  # filled in from column-map below
            }

    def _ensure_op_meta(session: Any, op_id_value: int) -> None:
        if op_id_value in op_meta:
            return
        row = session.execute(
            select(
                AgentRunOperation.ordinal, AgentRunOperation.op_name
            ).where(AgentRunOperation.id == op_id_value)
        ).first()
        if row is None:
            # Defensive: an orphan edge without an op should not
            # happen given the FK, but treat it as ordinal 0 / unknown.
            op_meta[op_id_value] = (0, "unknown")
        else:
            op_meta[op_id_value] = (int(row[0]), row[1])

    with factory() as session:
        # --- row edges -------------------------------------------------
        row_stmt = (
            select(
                LineageRowEdge.source_table,
                LineageRowEdge.target_table,
                LineageRowEdge.op_id,
            )
            .where(LineageRowEdge.run_id == run_id)
        )
        if op_id is not None:
            row_stmt = row_stmt.where(LineageRowEdge.op_id == op_id)
        row_count_by_key: dict[tuple[str, str, int], int] = {}
        for src, tgt, op_id_value in session.execute(row_stmt).all():
            key = (src, tgt, int(op_id_value))
            row_count_by_key[key] = row_count_by_key.get(key, 0) + 1
            _ensure_op_meta(session, int(op_id_value))
            _ensure_node(src)
            _ensure_node(tgt)

        # --- column map ------------------------------------------------
        col_stmt = (
            select(
                LineageColumnMap.source_table,
                LineageColumnMap.source_column,
                LineageColumnMap.target_table,
                LineageColumnMap.target_column,
                LineageColumnMap.transform_kind,
                LineageColumnMap.op_id,
            )
            .where(LineageColumnMap.run_id == run_id)
            .order_by(LineageColumnMap.id)
        )
        if op_id is not None:
            col_stmt = col_stmt.where(LineageColumnMap.op_id == op_id)
        for src, src_col, tgt, tgt_col, kind, op_id_value in session.execute(
            col_stmt
        ).all():
            _ensure_op_meta(session, int(op_id_value))
            # Some column-map rows have ``source_table = NULL`` (the
            # ``unknown_origin`` transform_kind).  Those don't anchor
            # an inter-table edge, but they still annotate the target
            # node's column list — so always add the target column.
            _ensure_node(tgt)
            target_node = nodes_by_fqn[tgt]
            if tgt_col not in target_node["columns"]:
                target_node["columns"].append(tgt_col)
            if src is None:
                continue
            _ensure_node(src)
            source_node = nodes_by_fqn[src]
            if src_col and src_col not in source_node["columns"]:
                source_node["columns"].append(src_col)
            key = (src, tgt, int(op_id_value))
            edge = edges_by_key.get(key)
            if edge is None:
                ordinal, op_name = op_meta[int(op_id_value)]
                edge = {
                    "id": f"{src}__{tgt}__{int(op_id_value)}",
                    "source": src,
                    "target": tgt,
                    "op_id": int(op_id_value),
                    "op_ordinal": ordinal,
                    "op_name": op_name,
                    "transform_kinds": [],
                    "column_pairs": [],
                    "row_edge_count": 0,
                }
                edges_by_key[key] = edge
            transform_kinds = cast(list[str], edge["transform_kinds"])
            column_pairs = cast(list[dict[str, Any]], edge["column_pairs"])
            if kind not in transform_kinds:
                transform_kinds.append(kind)
            column_pairs.append(
                {
                    "source_column": src_col,
                    "target_column": tgt_col,
                    "transform_kind": kind,
                }
            )

        # --- ensure row-only edges (no column-map row) are surfaced ---
        # An op that wrote rows but recorded zero column-map rows still
        # deserves a node-to-node edge so the DAG is complete.  This is
        # rare in practice (column-lineage is recorded for every PQL
        # primitive that records row edges since ) but keeps
        # the contract simple: every (src, tgt, op) row-edge triple
        # appears in the graph.
        for (src, tgt, op_id_value), n in row_count_by_key.items():
            key = (src, tgt, op_id_value)
            edge = edges_by_key.get(key)
            if edge is None:
                ordinal, op_name = op_meta[op_id_value]
                edges_by_key[key] = {
                    "id": f"{src}__{tgt}__{op_id_value}",
                    "source": src,
                    "target": tgt,
                    "op_id": op_id_value,
                    "op_ordinal": ordinal,
                    "op_name": op_name,
                    "transform_kinds": [],
                    "column_pairs": [],
                    "row_edge_count": n,
                }
            else:
                edge["row_edge_count"] = n

    # Stable ordering: nodes alphabetical, edges by (op_ordinal, source).
    nodes = sorted(nodes_by_fqn.values(), key=lambda n: n["id"])
    edges = sorted(
        edges_by_key.values(),
        key=lambda e: (e["op_ordinal"], e["source"], e["target"]),
    )

    return {
        "run_id": run_id,
        "op_id": op_id,
        "nodes": nodes,
        "edges": edges,
    }


__all__ = ["build_lineage_graph"]
