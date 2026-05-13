"""Phase 77.0.E — citations.py registry refactor.

Coverage:

* The four Phase-76 citation kinds (``dp`` / ``topic`` / ``user``
  / ``agent``) are listed in
  :func:`registered_citation_kinds`.
* ``register_citation_kind`` adds a new kind and the resolver
  picks it up on the next call.
* Duplicate-key registration is rejected.
* Behavior unchanged for existing kinds — covered by the
  pre-77.0 ``test_citation_render_phase76_7.py`` +
  ``test_sse_citations_phase76_6.py`` (15 tests must remain
  green).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.orm import Session

from pointlessql.api.main import app
from pointlessql.services.social.citations import (
    CitationKind,
    register_citation_kind,
    registered_citation_kinds,
    resolve_citations,
)


def test_existing_four_kinds_are_registered() -> None:
    """Phase-76 kinds survive the 77.0.E refactor."""
    kinds = registered_citation_kinds()
    assert "dp" in kinds
    assert "topic" in kinds
    assert "user" in kinds
    assert "agent" in kinds


def test_register_new_kind_makes_resolver_pick_it_up() -> None:
    """Adding a kind at runtime extends resolution.

    Simulates a 77.1+ sub-phase registering ``#example:`` —
    the resolver immediately starts rewriting tokens of that
    kind.  Uses a unique key to avoid colliding with real
    77.1+ work that will register ``#table:`` etc.
    """
    pattern = re.compile(r"#example77e:([a-z]+)")

    def _resolve(
        session: Session, workspace_id: int, slugs: set[object]
    ) -> set[str]:
        del session, workspace_id
        # Resolve every literal-string capture so the assertion
        # has a deterministic anchor regardless of DB state.
        return {s for s in slugs if isinstance(s, str)}

    def _render(match: re.Match[str], hits: set[str]) -> str:
        slug = match.group(1)
        if slug not in hits:
            return match.group(0)
        return f"[#example:{slug}](/example/{slug})"

    register_citation_kind(
        CitationKind(
            key="example77e",
            regex=pattern,
            resolve=_resolve,
            render=_render,
        )
    )

    out = resolve_citations(
        "see #example77e:foo for context",
        app.state.session_factory,
        workspace_id=1,
    )
    assert "[#example:foo](/example/foo)" in out
    assert "#example77e:foo" not in out


def test_register_duplicate_kind_rejected() -> None:
    """Re-registering the same key raises ValueError."""
    pattern = re.compile(r"#dummy:(.+)")

    def _resolve(
        session: Session, workspace_id: int, slugs: set[object]
    ) -> set[str]:
        del session, workspace_id, slugs
        return set()

    def _render(match: re.Match[str], hits: set[str]) -> str:
        del hits
        return match.group(0)

    with pytest.raises(ValueError, match="already registered"):
        register_citation_kind(
            CitationKind(
                key="dp",  # already registered in 77.0.E
                regex=pattern,
                resolve=_resolve,
                render=_render,
            )
        )
