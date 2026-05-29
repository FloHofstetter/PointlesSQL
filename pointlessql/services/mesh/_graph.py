"""Emergent mesh graph built from locally-declared input ports.

The mesh's dependency graph is never authored centrally — it *emerges*
from each product declaring its own upstreams.  This module reads every
product's ``upstream_product`` input ports, resolves each ``source_ref``
to a producing product in the same workspace, and assembles the result
as a cytoscape-shaped ``{"nodes": [...], "edges": [...]}`` graph (edge
direction = producer → consumer).

:func:`build_mesh_graph` returns the whole workspace; :func:`build_local_mesh`
returns the neighbourhood of one product (its upstreams + downstreams up
to *hops* away) for the product-detail Interop tab.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductInputPort,
    Domain,
)


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def _node(row: DataProduct, *, slug: str, domain: dict[str, Any] | None) -> dict[str, Any]:
    """Render one product as a cytoscape node dict."""
    ref = f"{row.catalog_name}.{row.schema_name}"
    return {
        "id": ref,
        "ref": ref,
        "catalog": row.catalog_name,
        "schema": row.schema_name,
        "uri": f"urn:pointlessql:product:{slug}:{row.catalog_name}:{row.schema_name}",
        "version": row.version,
        "domain": domain,
        "steward_user_id": row.steward_user_id,
        "sla_minutes": row.sla_minutes,
    }


def _resolve_graph(
    session: Any, *, workspace_id: int, slug: str
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Build the full node map + edge list for a workspace.

    Returns:
        ``(nodes_by_ref, edges)`` where every edge's ``source`` +
        ``target`` are present in ``nodes_by_ref`` (dangling
        ``source_ref`` values are dropped).
    """
    products = list(
        session.scalars(
            select(DataProduct).where(DataProduct.workspace_id == workspace_id)
        ).all()
    )
    domain_cache: dict[int, dict[str, Any] | None] = {}

    def _domain(domain_id: int | None) -> dict[str, Any] | None:
        if domain_id is None:
            return None
        if domain_id not in domain_cache:
            dom = session.get(Domain, domain_id)
            domain_cache[domain_id] = (
                {"id": dom.id, "slug": dom.slug, "name": dom.name} if dom is not None else None
            )
        return domain_cache[domain_id]

    nodes: dict[str, dict[str, Any]] = {}
    by_id: dict[int, str] = {}
    for product in products:
        ref = f"{product.catalog_name}.{product.schema_name}"
        nodes[ref] = _node(product, slug=slug, domain=_domain(product.domain_id))
        by_id[product.id] = ref

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for product in products:
        consumer_ref = f"{product.catalog_name}.{product.schema_name}"
        ports = list(
            session.scalars(
                select(DataProductInputPort).where(
                    DataProductInputPort.data_product_id == product.id,
                    DataProductInputPort.kind == "upstream_product",
                )
            ).all()
        )
        for port in ports:
            ref = (port.source_ref or "").strip()
            if ref not in nodes or ref == consumer_ref:
                continue
            key = (ref, consumer_ref, port.name)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "source": ref,
                    "target": consumer_ref,
                    "port_name": port.name,
                }
            )
    return nodes, edges


def _workspace_slug(session: Any, workspace_id: int) -> str:
    """Return the workspace slug, falling back to the id as a string."""
    from pointlessql.models import Workspace

    ws = session.get(Workspace, workspace_id)
    return ws.slug if ws is not None else str(workspace_id)


def build_mesh_graph(
    session_factory: _SessionFactory, *, workspace_id: int
) -> dict[str, Any]:
    """Return the whole workspace's emergent mesh graph.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace to graph.

    Returns:
        ``{"nodes": [...], "edges": [...]}`` — products as nodes,
        declared ``upstream_product`` inputs as producer→consumer edges.
    """
    with session_factory() as session:
        slug = _workspace_slug(session, workspace_id)
        nodes, edges = _resolve_graph(session, workspace_id=workspace_id, slug=slug)
    return {"nodes": list(nodes.values()), "edges": edges}


def build_local_mesh(
    session_factory: _SessionFactory,
    *,
    workspace_id: int,
    data_product_id: int,
    hops: int = 1,
) -> dict[str, Any]:
    """Return the neighbourhood graph around one product.

    Walks both directions — the product's upstreams and the products
    that declare it as an upstream — out to *hops* edges.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace the product lives in.
        data_product_id: The product at the centre of the neighbourhood.
        hops: How many edges to expand in each direction (min 1).

    Returns:
        ``{"nodes": [...], "edges": [...], "center": ref|None}`` — the
        induced sub-graph.  Empty when the product id is unknown.
    """
    hops = max(1, hops)
    with session_factory() as session:
        slug = _workspace_slug(session, workspace_id)
        center = session.get(DataProduct, data_product_id)
        if center is None or center.workspace_id != workspace_id:
            return {"nodes": [], "edges": [], "center": None}
        center_ref = f"{center.catalog_name}.{center.schema_name}"
        nodes, edges = _resolve_graph(session, workspace_id=workspace_id, slug=slug)

    adjacency: dict[str, set[str]] = {ref: set() for ref in nodes}
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])

    reachable: set[str] = {center_ref}
    frontier = {center_ref}
    for _ in range(hops):
        nxt: set[str] = set()
        for ref in frontier:
            nxt |= adjacency.get(ref, set())
        nxt -= reachable
        reachable |= nxt
        frontier = nxt
        if not frontier:
            break

    sub_nodes = [nodes[ref] for ref in reachable if ref in nodes]
    sub_edges = [e for e in edges if e["source"] in reachable and e["target"] in reachable]
    return {"nodes": sub_nodes, "edges": sub_edges, "center": center_ref}
