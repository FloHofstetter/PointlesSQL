"""Graph ordering primitives shared across every canvas consumer.

Both the dataframe SQL compiler and the scheduler's task-chain executor
walk a canvas DAG in dependency order.  They used to carry their own copy
of Kahn's algorithm; a single ``topo_sort`` here keeps the ordering — and
its cycle-detection contract — defined exactly once.

The sort is deterministic: ready nodes and their downstream neighbours
are visited in sorted id order, so two equivalent graphs always produce
the same node sequence (and therefore the same CTE names downstream).
The tie-break key is pluggable via ``sort_key`` so a consumer whose node
ids are numeric strings (the scheduler stamps ``str(job_task.id)``) gets
numeric ordering — ``"10"`` after ``"2"``, not before it — without the
dataframe consumers losing their plain lexical order (the default).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pointlessql.services.canvas_core._types import (
    CanvasEdge,
    CanvasNode,
    CompileError,
)


def _identity(node_id: str) -> Any:
    """Return *node_id* unchanged — the default lexical tie-break key."""
    return node_id


def topo_sort(
    nodes: list[CanvasNode],
    edges: list[CanvasEdge],
    errors: list[CompileError],
    *,
    sort_key: Callable[[str], Any] = _identity,
) -> list[CanvasNode] | None:
    """Order *nodes* so every edge points forward, via Kahn's algorithm.

    A cycle cannot be linearised, so it surfaces as a structured
    :class:`CompileError` rather than an infinite loop — callers treat a
    ``None`` return as "stop, the graph is malformed".

    Args:
        nodes: Every node in the canvas.
        edges: Directed edges; ``source_node_id`` precedes ``target_node_id``.
        errors: Accumulator a cycle error is appended to on failure.
        sort_key: Tie-break key applied to node ids when several nodes are
            simultaneously ready.  ``None`` (the default) sorts the raw
            string ids lexically — the behaviour the dataframe compiler
            relies on for stable CTE names.  Pass ``int`` when ids are
            numeric strings and numeric ordering is required.

    Returns:
        Nodes in dependency order, or ``None`` when a cycle is detected.
    """
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        incoming[edge.target_node_id].add(edge.source_node_id)
        outgoing[edge.source_node_id].add(edge.target_node_id)
    by_id = {n.id: n for n in nodes}
    ready = sorted([n.id for n in nodes if not incoming.get(n.id)], key=sort_key)
    ordered: list[str] = []
    while ready:
        nid = ready.pop(0)
        ordered.append(nid)
        for downstream in sorted(outgoing.get(nid, set()), key=sort_key):
            incoming[downstream].discard(nid)
            if not incoming[downstream]:
                ready.append(downstream)
                ready.sort(key=sort_key)
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


__all__ = ["topo_sort"]
