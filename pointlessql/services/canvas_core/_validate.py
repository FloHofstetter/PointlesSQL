"""Structural envelope validation, shared by every canvas consumer.

These checks are domain-agnostic: they care only about the shape of the
graph (non-empty, unique node/edge ids, edges that reference real nodes,
no self-loops), never about what a node *means*.  The dataframe compiler
runs this before topo-sort; the scheduler editor and the notebook builder
reuse the exact same gate so "duplicate node id" or "edge points at a
node that does not exist" reads identically across surfaces.
"""

from __future__ import annotations

from pointlessql.services.canvas_core._types import CanvasDoc, CompileError


def validate_envelope(doc: CanvasDoc, errors: list[CompileError]) -> bool:
    """Surface envelope problems before any ordering or compilation.

    Args:
        doc: The canvas document to check.
        errors: Accumulator structured problems are appended to.

    Returns:
        ``True`` when the document is well-formed enough for topo-sort to
        proceed; any envelope error blocks downstream work early.
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


__all__ = ["validate_envelope"]
