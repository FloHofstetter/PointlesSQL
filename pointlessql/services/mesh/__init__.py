"""Mesh-plane service layer — graph, polysemic identity, joins, health.

Re-exports the emergent-graph builder, the mesh-entity registry CRUD +
bindings, the shared-entity join helper, the point-in-time read
resolver, and the mesh-health rollup so callers do
``from pointlessql.services import mesh`` without reaching into the
private sub-modules.
"""

from __future__ import annotations

from pointlessql.services.mesh._entities import (
    add_binding,
    create_entity,
    delete_binding,
    delete_entity,
    entities_for_schema,
    list_bindings,
    list_entities,
    slugify,
)
from pointlessql.services.mesh._graph import build_local_mesh, build_mesh_graph
from pointlessql.services.mesh._health import mesh_health
from pointlessql.services.mesh._join_helper import joinable_columns
from pointlessql.services.mesh._point_in_time import resolve_as_of

__all__ = [
    "add_binding",
    "build_local_mesh",
    "build_mesh_graph",
    "create_entity",
    "delete_binding",
    "delete_entity",
    "entities_for_schema",
    "joinable_columns",
    "list_bindings",
    "list_entities",
    "mesh_health",
    "resolve_as_of",
    "slugify",
]
