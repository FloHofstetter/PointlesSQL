"""Graph-shaped lineage queries built on the mesh-graph substrate (D5).

The mesh graph (:mod:`pointlessql.services.mesh._graph`) already
materialises a workspace-wide ``producer → consumer`` graph from
declared input ports.  This module layers focused queries on top:

* :func:`find_upstream` — bounded BFS upstream from a product.
* :func:`find_downstream` — bounded BFS downstream from a product.
* :func:`find_shortest_path` — BFS one ↔ many between two products.
* :func:`cluster_by_domain` — group nodes by domain.

Each query returns plain dicts ready for JSON / cytoscape rendering;
filters (``filter_kind``, ``filter_domain``) are applied to the
returned set without changing edge direction.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from pointlessql.services.mesh._graph import build_mesh_graph
from pointlessql.types import SessionFactory


def _build_adjacency(
    factory: SessionFactory, *, workspace_id: int
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, list[str]]]:
    """Materialise ``(nodes_by_ref, upstream_adj, downstream_adj)``.

    Args:
        factory: Sessionmaker callable.
        workspace_id: Workspace scope.

    Returns:
        Triple where ``upstream_adj[X]`` lists refs *producing* X, and
        ``downstream_adj[X]`` lists refs *consuming* X.
    """
    graph = build_mesh_graph(factory, workspace_id=workspace_id)
    nodes_by_ref: dict[str, dict[str, Any]] = {node["ref"]: node for node in graph.get("nodes", [])}
    upstream_adj: dict[str, list[str]] = {ref: [] for ref in nodes_by_ref}
    downstream_adj: dict[str, list[str]] = {ref: [] for ref in nodes_by_ref}
    for edge in graph.get("edges", []):
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if src in nodes_by_ref and tgt in nodes_by_ref:
            downstream_adj[src].append(tgt)
            upstream_adj[tgt].append(src)
    return nodes_by_ref, upstream_adj, downstream_adj


def _matches_filters(
    node: dict[str, Any], *, filter_kind: str | None, filter_domain: str | None
) -> bool:
    """Apply optional kind / domain filters to one node dict."""
    if filter_domain is not None:
        node_domain = node.get("domain") or {}
        slug = node_domain.get("slug") if isinstance(node_domain, dict) else None
        if slug != filter_domain:
            return False
    if filter_kind is not None:
        kind = node.get("kind") or "data_product"
        if kind != filter_kind:
            return False
    return True


def _bfs_directed(
    start_ref: str,
    adjacency: dict[str, list[str]],
    *,
    depth: int,
) -> list[str]:
    """Return refs reachable within *depth* hops along *adjacency*."""
    visited: set[str] = {start_ref}
    order: list[str] = []
    frontier: deque[tuple[str, int]] = deque([(start_ref, 0)])
    while frontier:
        ref, current_depth = frontier.popleft()
        if current_depth >= depth:
            continue
        for neighbour in adjacency.get(ref, []):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            order.append(neighbour)
            frontier.append((neighbour, current_depth + 1))
    return order


def find_upstream(
    factory: SessionFactory,
    *,
    workspace_id: int,
    product_ref: str,
    depth: int = 3,
    filter_kind: str | None = None,
    filter_domain: str | None = None,
) -> list[dict[str, Any]]:
    """Return products upstream of *product_ref* within *depth* hops.

    Args:
        factory: Sessionmaker callable.
        workspace_id: Workspace scope.
        product_ref: ``catalog.schema`` of the focus product.
        depth: Max hop count (≥ 1).
        filter_kind: Optional ``kind`` filter applied to results.
        filter_domain: Optional domain ``slug`` filter applied to
            results.

    Returns:
        Ordered list of upstream node dicts (BFS order, no duplicates).

    Raises:
        ValueError: When ``depth < 1``.
        LookupError: When ``product_ref`` is not in the workspace.
    """
    if depth < 1:
        raise ValueError("depth must be ≥ 1")
    nodes, upstream_adj, _ = _build_adjacency(factory, workspace_id=workspace_id)
    if product_ref not in nodes:
        raise LookupError(f"product {product_ref!r} not found in workspace")
    refs = _bfs_directed(product_ref, upstream_adj, depth=depth)
    return [
        nodes[ref]
        for ref in refs
        if _matches_filters(nodes[ref], filter_kind=filter_kind, filter_domain=filter_domain)
    ]


def find_downstream(
    factory: SessionFactory,
    *,
    workspace_id: int,
    product_ref: str,
    depth: int = 3,
    filter_kind: str | None = None,
    filter_domain: str | None = None,
) -> list[dict[str, Any]]:
    """Mirror of :func:`find_upstream` for downstream consumers."""
    if depth < 1:
        raise ValueError("depth must be ≥ 1")
    nodes, _, downstream_adj = _build_adjacency(factory, workspace_id=workspace_id)
    if product_ref not in nodes:
        raise LookupError(f"product {product_ref!r} not found in workspace")
    refs = _bfs_directed(product_ref, downstream_adj, depth=depth)
    return [
        nodes[ref]
        for ref in refs
        if _matches_filters(nodes[ref], filter_kind=filter_kind, filter_domain=filter_domain)
    ]


def find_shortest_path(
    factory: SessionFactory,
    *,
    workspace_id: int,
    source_ref: str,
    target_ref: str,
) -> list[str] | None:
    """Return the shortest ``producer → consumer`` path or ``None``.

    Walks the downstream-adjacency from *source_ref* via BFS until
    *target_ref* is hit, then unwinds the predecessor chain.

    Raises:
        LookupError: When either endpoint is not in the workspace.
    """
    nodes, _, downstream_adj = _build_adjacency(factory, workspace_id=workspace_id)
    if source_ref not in nodes:
        raise LookupError(f"source product {source_ref!r} not found")
    if target_ref not in nodes:
        raise LookupError(f"target product {target_ref!r} not found")
    if source_ref == target_ref:
        return [source_ref]

    predecessor: dict[str, str] = {}
    visited: set[str] = {source_ref}
    queue: deque[str] = deque([source_ref])
    while queue:
        current = queue.popleft()
        for neighbour in downstream_adj.get(current, []):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            predecessor[neighbour] = current
            if neighbour == target_ref:
                path = [neighbour]
                while path[-1] != source_ref:
                    path.append(predecessor[path[-1]])
                return list(reversed(path))
            queue.append(neighbour)
    return None


def cluster_by_domain(
    factory: SessionFactory,
    *,
    workspace_id: int,
) -> dict[str, list[dict[str, Any]]]:
    """Group every product in the workspace by its domain slug.

    Products without a domain land in the ``"(no domain)"`` bucket.
    """
    nodes, _, _ = _build_adjacency(factory, workspace_id=workspace_id)
    clusters: dict[str, list[dict[str, Any]]] = {}
    for node in nodes.values():
        domain = node.get("domain") or {}
        slug = "(no domain)"
        if isinstance(domain, dict):
            raw_slug = domain.get("slug")
            if isinstance(raw_slug, str) and raw_slug:
                slug = raw_slug
        clusters.setdefault(slug, []).append(node)
    return {slug: sorted(bucket, key=lambda n: n["ref"]) for slug, bucket in clusters.items()}
