"""Entity declarations + cross-product entity links (F3).

Two surfaces:

* ``_crud`` — declare/list/link entities owned by a data product.
* ``_resolver`` — global polysemic-identity resolution via the
  ``same_as`` graph.
"""

from __future__ import annotations

from pointlessql.services.entities._crud import (
    declare_entity,
    delete_entity,
    link_entities,
    list_entities,
    list_links,
    unlink_entities,
)
from pointlessql.services.entities._resolver import (
    EntityIdentity,
    resolve_entity_by_pk,
    resolve_same_as_graph,
)

__all__ = [
    "EntityIdentity",
    "declare_entity",
    "delete_entity",
    "link_entities",
    "list_entities",
    "list_links",
    "resolve_entity_by_pk",
    "resolve_same_as_graph",
    "unlink_entities",
]
