"""Data-product lifecycle service layer.

Re-exports the state-machine + CRUD primitives so callers do
``from pointlessql.services import lifecycle as lifecycle_service``
without reaching into the private sub-modules.
"""

from __future__ import annotations

from pointlessql.services.lifecycle._crud import (
    LIFECYCLE_CHANGED_ACTION,
    LIFECYCLE_PROPOSED_ACTION,
    LifecycleHistoryEntry,
    list_history,
    propose_transition,
    read_state,
    transition,
)
from pointlessql.services.lifecycle._transitions import (
    ALLOWED_TRANSITIONS,
    LifecycleTransitionError,
    allowed_targets,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "LIFECYCLE_CHANGED_ACTION",
    "LIFECYCLE_PROPOSED_ACTION",
    "LifecycleHistoryEntry",
    "LifecycleTransitionError",
    "allowed_targets",
    "list_history",
    "propose_transition",
    "read_state",
    "transition",
]
