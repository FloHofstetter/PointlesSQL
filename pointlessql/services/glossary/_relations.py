"""Glossary-term knowledge-graph: relations + graph traversal.

The relations table builds an emergent vocabulary graph next to the
column-binding surface.  This module owns relation CRUD plus a bounded
BFS traversal that powers the term-graph drawer in the glossary UI.
"""

from __future__ import annotations

import datetime
from collections import deque
from typing import Any

from sqlalchemy import select

from pointlessql.models.catalog._glossary import (
    GLOSSARY_TERM_RELATION_KINDS,
    GlossaryTerm,
    GlossaryTermRelation,
)
from pointlessql.types import SessionFactory


def _now() -> datetime.datetime:
    """UTC wall-clock used for ``created_at``."""
    return datetime.datetime.now(datetime.UTC)


def add_relation(
    factory: SessionFactory,
    *,
    source_term_id: int,
    target_term_id: int,
    kind: str,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Insert one :class:`GlossaryTermRelation`.  Idempotent on identity.

    Args:
        factory: Sessionmaker callable.
        source_term_id: FK on ``glossary_terms.id``.
        target_term_id: FK on ``glossary_terms.id``.
        kind: One of :data:`GLOSSARY_TERM_RELATION_KINDS`.
        created_by_user_id: Author of the relation.

    Returns:
        Dict of the persisted row.

    Raises:
        ValueError: When *kind* is unknown or source == target.
    """
    if kind not in GLOSSARY_TERM_RELATION_KINDS:
        raise ValueError(f"unknown relation kind: {kind!r}")
    if source_term_id == target_term_id:
        raise ValueError("source and target term must differ")
    with factory() as session:
        existing = session.scalar(
            select(GlossaryTermRelation).where(
                GlossaryTermRelation.source_term_id == source_term_id,
                GlossaryTermRelation.target_term_id == target_term_id,
                GlossaryTermRelation.kind == kind,
            )
        )
        if existing is not None:
            row = existing
        else:
            row = GlossaryTermRelation(
                source_term_id=source_term_id,
                target_term_id=target_term_id,
                kind=kind,
                created_by_user_id=created_by_user_id,
                created_at=_now(),
            )
            session.add(row)
            session.commit()
        return {
            "id": row.id,
            "source_term_id": row.source_term_id,
            "target_term_id": row.target_term_id,
            "kind": row.kind,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


def delete_relation(
    factory: SessionFactory,
    *,
    relation_id: int,
) -> bool:
    """Delete one relation by PK.  Returns ``True`` on removal."""
    with factory() as session:
        row = session.get(GlossaryTermRelation, relation_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_relations(
    factory: SessionFactory,
    *,
    term_id: int,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Return relations incident on *term_id*.

    Args:
        factory: Sessionmaker callable.
        term_id: Glossary term PK.
        direction: ``"outgoing"``, ``"incoming"`` or ``"both"``.

    Returns:
        Sorted list of relation dicts.
    """
    with factory() as session:
        stmt = select(GlossaryTermRelation)
        if direction == "outgoing":
            stmt = stmt.where(GlossaryTermRelation.source_term_id == term_id)
        elif direction == "incoming":
            stmt = stmt.where(GlossaryTermRelation.target_term_id == term_id)
        else:
            stmt = stmt.where(
                (GlossaryTermRelation.source_term_id == term_id)
                | (GlossaryTermRelation.target_term_id == term_id)
            )
        rows = session.scalars(stmt.order_by(GlossaryTermRelation.created_at)).all()
        return [
            {
                "id": row.id,
                "source_term_id": row.source_term_id,
                "target_term_id": row.target_term_id,
                "kind": row.kind,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]


def term_graph(
    factory: SessionFactory,
    *,
    root_term_id: int,
    depth: int = 2,
) -> dict[str, Any]:
    """BFS the term-relation graph starting at *root_term_id*.

    Args:
        factory: Sessionmaker callable.
        root_term_id: Term PK to start at.
        depth: Maximum BFS depth (bounded; ``1`` returns immediate
            neighbours only).

    Returns:
        ``{"nodes": [...], "edges": [...]}`` shape ready for
        cytoscape-style graph rendering.  Nodes are de-duplicated term
        dicts (``id``, ``slug``, ``term``); edges carry ``source``,
        ``target``, ``kind``.

    Raises:
        LookupError: When *root_term_id* does not exist.
        ValueError: When ``depth`` is not positive.
    """
    if depth <= 0:
        raise ValueError("depth must be positive")
    with factory() as session:
        root = session.get(GlossaryTerm, root_term_id)
        if root is None:
            raise LookupError(f"term {root_term_id} not found")

        nodes: dict[int, dict[str, Any]] = {
            root.id: {"id": root.id, "slug": root.slug, "term": root.term},
        }
        edges: list[dict[str, Any]] = []
        seen_edges: set[tuple[int, int, str]] = set()
        frontier: deque[tuple[int, int]] = deque([(root.id, 0)])
        visited: set[int] = {root.id}

        while frontier:
            current, current_depth = frontier.popleft()
            if current_depth >= depth:
                continue
            relations = session.scalars(
                select(GlossaryTermRelation).where(
                    (GlossaryTermRelation.source_term_id == current)
                    | (GlossaryTermRelation.target_term_id == current),
                )
            ).all()
            for rel in relations:
                edge_id = (rel.source_term_id, rel.target_term_id, rel.kind)
                if edge_id not in seen_edges:
                    seen_edges.add(edge_id)
                    edges.append({
                        "source": rel.source_term_id,
                        "target": rel.target_term_id,
                        "kind": rel.kind,
                    })
                neighbour_id = (
                    rel.target_term_id
                    if rel.source_term_id == current
                    else rel.source_term_id
                )
                if neighbour_id in visited:
                    continue
                neighbour_row = session.get(GlossaryTerm, neighbour_id)
                if neighbour_row is None:
                    continue
                nodes[neighbour_id] = {
                    "id": neighbour_row.id,
                    "slug": neighbour_row.slug,
                    "term": neighbour_row.term,
                }
                visited.add(neighbour_id)
                frontier.append((neighbour_id, current_depth + 1))

        return {
            "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
            "edges": edges,
        }
