"""Polysemic entity-identity resolution via the ``same_as`` graph.

Given a row's PK in one product, find the *global* identity it
represents — i.e. every entity reachable through ``same_as`` links
across the workspace.  Used by lineage tooling, joins planner, and
the auto-discovery candidate scorer.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProduct
from pointlessql.models.catalog._entity import DataProductEntity, EntityLink
from pointlessql.types import SessionFactory


@dataclasses.dataclass(frozen=True)
class EntityIdentity:
    """One global polysemic-identity cluster.

    Attributes:
        canonical_entity_id: The lowest-PK entity in the cluster,
            chosen as the canonical handle.
        members: Sorted list of entity dicts in the same ``same_as``
            cluster.  Each dict carries ``id``, ``data_product_id``,
            ``entity_name`` and ``source_table``.
    """

    canonical_entity_id: int
    members: list[dict[str, Any]]


def resolve_same_as_graph(
    factory: SessionFactory,
    *,
    entity_id: int,
) -> EntityIdentity:
    """Walk the ``same_as`` graph starting at *entity_id*.

    BFS through both link directions; the cluster is the connected
    component reachable via ``same_as`` links.

    Args:
        factory: Sessionmaker callable.
        entity_id: Entity PK to start the walk at.

    Returns:
        :class:`EntityIdentity` with the canonical PK + sorted members.

    Raises:
        LookupError: When *entity_id* does not exist.
    """
    with factory() as session:
        root = session.get(DataProductEntity, entity_id)
        if root is None:
            raise LookupError(f"entity {entity_id} not found")

        visited: dict[int, DataProductEntity] = {entity_id: root}
        queue: deque[int] = deque([entity_id])
        while queue:
            current = queue.popleft()
            link_rows = session.scalars(
                select(EntityLink).where(
                    (
                        (EntityLink.source_entity_id == current)
                        | (EntityLink.target_entity_id == current)
                    ),
                    EntityLink.kind == "same_as",
                )
            ).all()
            for link in link_rows:
                neighbour = (
                    link.target_entity_id
                    if link.source_entity_id == current
                    else link.source_entity_id
                )
                if neighbour in visited:
                    continue
                neighbour_row = session.get(DataProductEntity, neighbour)
                if neighbour_row is None:
                    continue
                visited[neighbour] = neighbour_row
                queue.append(neighbour)

        members = [
            {
                "id": row.id,
                "data_product_id": row.data_product_id,
                "entity_name": row.entity_name,
                "source_table": row.source_table,
            }
            for row in sorted(visited.values(), key=lambda r: r.id)
        ]
        canonical = min(visited.keys())
        return EntityIdentity(canonical_entity_id=canonical, members=members)


def resolve_entity_by_pk(
    factory: SessionFactory,
    *,
    catalog: str,
    schema: str,
    entity_name: str,
) -> EntityIdentity | None:
    """Look up a polysemic identity for ``catalog.schema.entity_name``.

    Args:
        factory: Sessionmaker callable.
        catalog: UC catalog.
        schema: UC schema.
        entity_name: Entity label inside the owning product.

    Returns:
        The :class:`EntityIdentity` cluster, or ``None`` when no entity
        with that name exists in the product.
    """
    with factory() as session:
        product = session.scalar(
            select(DataProduct).where(
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        )
        if product is None:
            return None
        entity = session.scalar(
            select(DataProductEntity).where(
                DataProductEntity.data_product_id == product.id,
                DataProductEntity.entity_name == entity_name,
            )
        )
        if entity is None:
            return None
        return resolve_same_as_graph(factory, entity_id=entity.id)
