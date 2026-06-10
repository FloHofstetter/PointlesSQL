"""Allowed lifecycle transitions + guard predicates.

The state machine is intentionally small and one-directional except for
``archived → active`` (restore):

    draft → active → deprecated → retired → archived
    active → archived           (shortcut when no consumer ever attached)
    archived → active           (restore)

Any other transition raises :class:`LifecycleTransitionError`; the route
layer translates it to HTTP 409.
"""

from __future__ import annotations

from pointlessql.models import LIFECYCLE_STATES

#: Map of ``from_state -> {valid_to_states}``.  Every state from
#: :data:`pointlessql.models.LIFECYCLE_STATES` appears as a key so a
#: caller can ask "what is reachable from here?" without a None branch.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"active", "archived"}),
    "active": frozenset({"deprecated", "archived"}),
    "deprecated": frozenset({"retired", "active"}),
    "retired": frozenset({"archived"}),
    "archived": frozenset({"active"}),
}


class LifecycleTransitionError(ValueError):
    """Raised when a transition is not allowed by the state machine."""


def allowed_targets(state: str) -> frozenset[str]:
    """Return the set of states reachable from *state*.

    Args:
        state: A value from :data:`LIFECYCLE_STATES`.

    Returns:
        Frozen set of valid target states.  Empty only if *state* is
        unknown.
    """
    return ALLOWED_TRANSITIONS.get(state, frozenset())


def assert_transition(current: str, target: str) -> None:
    """Raise :class:`LifecycleTransitionError` if ``current → target`` is invalid.

    Args:
        current: The product's current ``lifecycle_state``.
        target: The requested target state.

    Raises:
        LifecycleTransitionError: When *target* is not in
            :data:`LIFECYCLE_STATES` or not reachable from *current*.
    """
    if target not in LIFECYCLE_STATES:
        raise LifecycleTransitionError(f"target state {target!r} not in {sorted(LIFECYCLE_STATES)}")
    if target == current:
        raise LifecycleTransitionError(f"product is already in state {current!r}; nothing to do")
    if target not in allowed_targets(current):
        raise LifecycleTransitionError(
            f"cannot transition from {current!r} to {target!r}; "
            f"reachable: {sorted(allowed_targets(current))}"
        )
