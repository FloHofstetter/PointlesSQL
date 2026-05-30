"""Entity declarations + cross-product entity links (F3).

Two surfaces:

* ``_crud`` — declare/list/link entities owned by a data product.
* ``_resolver`` — global polysemic-identity resolution via the
  ``same_as`` graph.
"""

from __future__ import annotations

from pointlessql.services.entities._candidates import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    CandidateScore,
    discover_candidates,
    score_combined,
    score_column_similarity,
    score_pk_overlap,
)
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
from pointlessql.services.entities._review_queue import (
    accept_candidate,
    defer_candidate,
    list_candidates_by_decision,
    list_pending_candidates,
    reject_candidate,
)

__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "CandidateScore",
    "EntityIdentity",
    "accept_candidate",
    "declare_entity",
    "defer_candidate",
    "delete_entity",
    "discover_candidates",
    "link_entities",
    "list_candidates_by_decision",
    "list_entities",
    "list_links",
    "list_pending_candidates",
    "reject_candidate",
    "resolve_entity_by_pk",
    "resolve_same_as_graph",
    "score_column_similarity",
    "score_combined",
    "score_pk_overlap",
    "unlink_entities",
]
