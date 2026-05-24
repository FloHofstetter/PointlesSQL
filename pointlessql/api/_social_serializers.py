"""Shared JSON serialisers across the social route surface.

Phase 79.4 extraction.  Three pieces of duplication concentrated
on the agent-on-behalf-of payload shape:

* ``_agent_payload(agent: Agent | None)`` lived once in
  ``data_products_routes/reviews.py`` and once in
  ``data_products_routes/endorsements.py`` as bit-identical
  helpers.
* Two more sites built the same dict inline as part of an
  ``agent_map = {id: {...} for a in agents}`` comprehension
  (``comments.py`` and ``social_routes/_polymorphic_handlers.py``).

This module exposes :func:`agent_payload` as the single source of
truth so adding a new agent-side field (e.g. a future ``is_human``
discriminator) flips it across all four sites.

What this module deliberately does NOT extract: the
``_serialise_comment`` / ``_serialise_endorsement`` /
``_serialise_review`` envelopes.  Those have *intentionally*
different JSON shapes between the DP-specific routes (which use
``data_product_id``) and the polymorphic routes (which use
``social_target_id``) — see locked decision #3.
Forcing a unified serialiser would either break backward compat
for pre-77 clients or hide the polymorphic addressing key from
new clients.  The decision gate in the Phase-79 plan documents
the choice to skip that consolidation.
"""

from __future__ import annotations

from typing import Any

from pointlessql.models import Agent


def agent_payload(agent: Agent | None) -> dict[str, Any] | None:
    """Render an :class:`Agent` ORM row as a JSON-friendly dict.

    Returns ``None`` when *agent* is ``None`` so callers can chain
    ``agent_payload(session.get(Agent, id))`` without a separate
    null check.

    Args:
        agent: The agent row to serialise, or ``None`` when the
            comment / endorsement / review was authored directly
            by the principal (no agent intermediary).

    Returns:
        ``None`` iff *agent* is ``None``; otherwise a dict with
        ``slug`` / ``display_name`` / ``avatar_kind`` /
        ``is_verified`` / ``principal_user_id`` keys.
    """
    if agent is None:
        return None
    return {
        "slug": agent.slug,
        "display_name": agent.display_name,
        "avatar_kind": agent.avatar_kind,
        "is_verified": bool(agent.is_verified),
        "principal_user_id": agent.principal_user_id,
    }
