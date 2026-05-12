"""``GET /api/data-products/{catalog}/{schema}/lineage`` — cytoscape graph."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models import LineageRowEdge

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/lineage")
async def get_data_product_lineage(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return a minimal cytoscape graph of the product's tables + neighbours.

    Each declared table becomes a node; one-hop producers (via
    ``lineage_row_edges.source_table``) and consumers (via
    ``target_table``) are included so the steward sees what flows
    into and out of the product.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"nodes": [...], "edges": [...]}`` in the cytoscape data
        shape (same as ``/api/models/.../lineage``).
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    _row, contract, _email, _display = load_one(
        factory, workspace_id, catalog, schema
    )

    table_fqns = {f"{catalog}.{schema}.{t.name}" for t in contract.tables}
    nodes: dict[str, dict[str, Any]] = {
        fqn: {
            "data": {
                "id": fqn,
                "label": fqn.split(".")[-1],
                "kind": "product_table",
            }
        }
        for fqn in table_fqns
    }
    edges: list[dict[str, Any]] = []

    if not table_fqns:
        return {"nodes": [], "edges": []}

    with factory() as session:
        inbound = session.execute(
            select(LineageRowEdge.source_table, LineageRowEdge.target_table)
            .where(LineageRowEdge.target_table.in_(table_fqns))
            .distinct()
        ).all()
        for src, tgt in inbound:
            if src and src not in nodes:
                nodes[src] = {
                    "data": {"id": src, "label": src.split(".")[-1], "kind": "producer"}
                }
            edges.append(
                {"data": {"source": src, "target": tgt, "kind": "produces"}}
            )

        outbound = session.execute(
            select(LineageRowEdge.source_table, LineageRowEdge.target_table)
            .where(LineageRowEdge.source_table.in_(table_fqns))
            .distinct()
        ).all()
        for src, tgt in outbound:
            if tgt and tgt not in nodes:
                nodes[tgt] = {
                    "data": {"id": tgt, "label": tgt.split(".")[-1], "kind": "consumer"}
                }
            edges.append(
                {"data": {"source": src, "target": tgt, "kind": "consumed_by"}}
            )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }
