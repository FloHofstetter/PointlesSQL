"""Genie Ontology — authority ranking over the lineage table graph.

A small, self-improving context layer: instead of hand-curating which
tables a Genie space should anchor on, this module ranks the workspace's
tables by a PageRank-style authority score computed over the directed
table graph already implied by lineage (``source_table -> target_table``
edges in ``lineage_row_edges``).  Tables that many well-connected sources
feed into — the canonical marts a lakehouse converges on — float to the
top, and those become the auto-suggested context for a space.

Only data that already exists is used (the lineage edge store); pulling
business meaning from connected workplace apps (Drive / Jira / Slack) is
a separate ingest concern and stays out of scope here.  PageRank is
hand-rolled (no ``networkx`` dependency) over the typically-small
per-workspace table graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import LineageRowEdge

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_DAMPING = 0.85
_MAX_ITERATIONS = 100
_CONVERGENCE_TOL = 1e-9


def _load_table_edges(factory: sessionmaker[Session], workspace_id: int) -> list[tuple[str, str]]:
    """Return the workspace's distinct ``(source_table, target_table)`` edges.

    Self-loops are dropped — a table feeding itself adds no authority
    signal and would only inflate its own rank.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace whose lineage edges to read.

    Returns:
        De-duplicated directed table edges.
    """
    with factory() as session:
        rows = session.execute(
            select(LineageRowEdge.source_table, LineageRowEdge.target_table)
            .where(LineageRowEdge.workspace_id == workspace_id)
            .distinct()
        ).all()
    return [(source, target) for source, target in rows if source != target]


def _pagerank(
    nodes: set[str],
    out_edges: dict[str, list[str]],
    *,
    damping: float = _DAMPING,
) -> dict[str, float]:
    """Compute PageRank over a directed graph.

    A standard iterative power method with dangling-node mass
    redistribution, so a table with no outgoing lineage still passes its
    authority on uniformly rather than leaking it.

    Args:
        nodes: Every table participating in the graph.
        out_edges: ``source -> [distinct targets]`` adjacency.
        damping: Teleport damping factor (conventionally 0.85).

    Returns:
        ``table -> rank`` with the ranks summing to ~1.0.
    """
    count = len(nodes)
    if count == 0:
        return {}
    rank = {node: 1.0 / count for node in nodes}
    dangling = [node for node in nodes if not out_edges.get(node)]
    base = (1.0 - damping) / count
    for _ in range(_MAX_ITERATIONS):
        dangling_mass = damping * sum(rank[node] for node in dangling) / count
        updated = {node: base + dangling_mass for node in nodes}
        for source, targets in out_edges.items():
            if not targets:
                continue
            share = damping * rank[source] / len(targets)
            for target in targets:
                updated[target] += share
        delta = sum(abs(updated[node] - rank[node]) for node in nodes)
        rank = updated
        if delta < _CONVERGENCE_TOL:
            break
    return rank


def compute_table_authority(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Rank the workspace's lineage-connected tables by authority.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace to rank within.
        limit: Max ranked tables to return.

    Returns:
        Tables ordered by descending authority, each
        ``{"table", "score", "in_degree", "out_degree"}``; ties break on
        the table name so the order is deterministic.
    """
    edges = _load_table_edges(factory, workspace_id)
    nodes: set[str] = set()
    out_edges: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {}
    out_degree: dict[str, int] = {}
    for source, target in edges:
        nodes.add(source)
        nodes.add(target)
        targets = out_edges.setdefault(source, [])
        if target not in targets:
            targets.append(target)
        in_degree[target] = in_degree.get(target, 0) + 1
        out_degree[source] = out_degree.get(source, 0) + 1

    rank = _pagerank(nodes, out_edges)
    items = [
        {
            "table": node,
            "score": round(rank.get(node, 0.0), 6),
            "in_degree": in_degree.get(node, 0),
            "out_degree": out_degree.get(node, 0),
        }
        for node in nodes
    ]
    items.sort(key=lambda item: (-float(item["score"]), str(item["table"])))
    return items[:limit]


def suggest_tables_for_space(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    curated: list[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the top-authority tables a space has not yet curated.

    Powers the "suggested tables" affordance so a curator can grow a
    space's context from the lineage graph instead of typing FQNs by
    hand.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace to rank within.
        curated: The space's already-curated table FQNs (excluded).
        limit: Max suggestions to return.

    Returns:
        Up to *limit* ranked-table dicts not already in *curated*.
    """
    curated_set = {entry.strip() for entry in curated}
    ranked = compute_table_authority(
        factory, workspace_id=workspace_id, limit=limit + len(curated_set) + 50
    )
    fresh = [item for item in ranked if item["table"] not in curated_set]
    return fresh[:limit]
