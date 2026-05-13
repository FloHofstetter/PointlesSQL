"""Cross-entity citations (Phase 76.6 + 77.0.E registry refactor).

Renders ``#dp:cat.schema`` / ``#topic:slug`` / ``#user:email`` /
``#agent:slug`` tokens inside a markdown body into HTML anchors.
Validation runs at *render* time, not at POST time — a citation
to a deleted entity gracefully degrades to literal text.

The Phase 77.0.E refactor lifts the four hand-rolled regex /
resolve / render branches into a single
``_CITATION_KINDS: list[CitationKind]`` registry.  Each entry is
a frozen dataclass with three callables:

* ``regex`` — the ``re.Pattern`` matching the kind's tokens
* ``resolve`` — turns the set of captured groups into the lookup
  result the renderer needs (callable that takes a Session +
  workspace_id + set of matched groups, returns whatever the
  render fn understands)
* ``render`` — the ``re.sub`` replacement callable.  Receives the
  match + the resolver's output; returns either an anchor
  markdown string or the original token (literal fallback).

Phase 77.1+ adds new kinds (``#table:cat.sch.tbl``,
``#model:cat.sch.name``, ``#branch:<fqn>``, ``#run:<uuid>``,
``#notebook:<uuid>``, ``#query:<slug>``) by appending one
dataclass per kind to the registry.  Zero behaviour drift for
the four existing kinds.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._topic import Topic


@dataclass(frozen=True)
class CitationKind:
    """One citation kind registered with the resolver.

    Attributes:
        key: Short string used for diagnostics + future kind
            lookups (e.g. ``'dp'``, ``'table'``).
        regex: Compiled pattern that matches all instances of
            this kind's tokens within a markdown body.
        resolve: Bound function that takes the active session,
            tenant ``workspace_id``, and the deduplicated set of
            captured-group tuples; returns an opaque object that
            ``render`` understands (e.g. a set of valid keys,
            a dict mapping keys to label data).
        render: ``re.sub`` callback.  Receives the match plus the
            resolver output and returns the replacement string —
            either an ``[label](href)`` markdown anchor or
            ``match.group(0)`` (literal fallback).
    """

    key: str
    regex: re.Pattern[str]
    resolve: Callable[[Session, int, set[Any]], Any]
    render: Callable[[re.Match[str], Any], str]


# ---------------------------------------------------------------------------
# Kind implementations
# ---------------------------------------------------------------------------


_DP_CITE_RE = re.compile(r"#dp:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")


def _resolve_dp(
    session: Session, workspace_id: int, pairs: set[Any]
) -> set[tuple[str, str]]:
    """Return the subset of ``(catalog, schema)`` pairs that exist."""
    if not pairs:
        return set()
    rows = session.execute(
        select(DataProduct.catalog_name, DataProduct.schema_name).where(
            DataProduct.workspace_id == workspace_id,
        )
    ).all()
    present = {(c, s) for c, s in rows}
    return present & pairs


def _render_dp(
    match: re.Match[str], hits: set[tuple[str, str]]
) -> str:
    """Build the anchor for ``#dp:cat.sch`` or pass through."""
    catalog, schema = match.group(1), match.group(2)
    if (catalog, schema) not in hits:
        return match.group(0)
    return f"[#{catalog}.{schema}](/data-products/{catalog}/{schema})"


_TOPIC_CITE_RE = re.compile(r"#topic:([a-z0-9][a-z0-9-]{1,60})")


def _resolve_topic(
    session: Session, workspace_id: int, slugs: set[Any]
) -> set[str]:
    """Return the subset of topic slugs that exist."""
    if not slugs:
        return set()
    rows = session.execute(
        select(Topic.slug).where(
            Topic.workspace_id == workspace_id,
            Topic.slug.in_(slugs),
        )
    ).all()
    return {s for (s,) in rows}


def _render_topic(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#topic:slug`` or pass through."""
    slug = match.group(1)
    if slug not in hits:
        return match.group(0)
    return f"[#{slug}](/topics/{slug})"


_USER_CITE_RE = re.compile(r"#user:([\w.+-]+@[\w-]+\.[\w.-]+)")


def _resolve_user(
    session: Session, workspace_id: int, emails: set[Any]
) -> dict[str, tuple[int, str | None]]:
    """Return ``{email: (user_id, display_name)}`` for matches."""
    del workspace_id  # users are not workspace-scoped for citations
    if not emails:
        return {}
    rows = session.execute(
        select(User.id, User.email, User.display_name).where(
            User.email.in_(emails)
        )
    ).all()
    return {
        str(email): (int(uid), display_name)
        for uid, email, display_name in rows
    }


def _render_user(
    match: re.Match[str], hits: dict[str, tuple[int, str | None]]
) -> str:
    """Build the anchor for ``#user:email`` or pass through."""
    email = match.group(1)
    hit = hits.get(email)
    if hit is None:
        return match.group(0)
    user_id, display_name = hit
    label = display_name or email
    return f"[@{label}](/users/{user_id})"


_AGENT_CITE_RE = re.compile(r"#agent:([a-z0-9][a-z0-9-]{1,60})")


def _resolve_agent(
    session: Session, workspace_id: int, slugs: set[Any]
) -> set[str]:
    """Return the subset of agent slugs that exist."""
    if not slugs:
        return set()
    rows = session.execute(
        select(Agent.slug).where(
            Agent.workspace_id == workspace_id,
            Agent.slug.in_(slugs),
        )
    ).all()
    return {s for (s,) in rows}


def _render_agent(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#agent:slug`` or pass through."""
    slug = match.group(1)
    if slug not in hits:
        return match.group(0)
    return f"[@{slug}](/agents/{slug})"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_CITATION_KINDS: list[CitationKind] = [
    CitationKind(
        key="dp",
        regex=_DP_CITE_RE,
        resolve=_resolve_dp,
        render=_render_dp,
    ),
    CitationKind(
        key="topic",
        regex=_TOPIC_CITE_RE,
        resolve=_resolve_topic,
        render=_render_topic,
    ),
    CitationKind(
        key="user",
        regex=_USER_CITE_RE,
        resolve=_resolve_user,
        render=_render_user,
    ),
    CitationKind(
        key="agent",
        regex=_AGENT_CITE_RE,
        resolve=_resolve_agent,
        render=_render_agent,
    ),
]


def register_citation_kind(kind: CitationKind) -> None:
    """Register a new citation kind.

    Args:
        kind: The :class:`CitationKind` to add to the registry.
            Later Phase-77 sub-phases call this once per
            new entity type (table / model / branch / run / …).

    Raises:
        ValueError: If a kind with the same ``key`` is already
            registered.
    """
    if any(existing.key == kind.key for existing in _CITATION_KINDS):
        msg = f"citation kind {kind.key!r} already registered"
        raise ValueError(msg)
    _CITATION_KINDS.append(kind)


def registered_citation_kinds() -> tuple[str, ...]:
    """Return every currently-registered citation kind key."""
    return tuple(k.key for k in _CITATION_KINDS)


# ---------------------------------------------------------------------------
# Public entry point — preserved Phase-76.6 signature
# ---------------------------------------------------------------------------


def resolve_citations(
    body_md: str,
    session_factory: Any,
    workspace_id: int,
) -> str:
    """Replace cite tokens in *body_md* with anchor markup.

    Args:
        body_md: Raw markdown body — possibly carrying cite
            tokens.  Returned verbatim when no tokens match.
        session_factory: SQLAlchemy session factory.
        workspace_id: Tenant scope used to filter the per-kind
            resolution lookups.

    Returns:
        A string with every resolvable cite token replaced by
        ``[label](href)`` (markdown anchor).  Unresolvable tokens
        stay literal.
    """
    if not body_md or "#" not in body_md:
        return body_md

    with session_factory() as session:
        hits_per_kind: dict[str, Any] = {}
        for kind in _CITATION_KINDS:
            captured = {
                m if isinstance(m, str) else tuple(m)
                for m in kind.regex.findall(body_md)
            }
            hits_per_kind[kind.key] = kind.resolve(
                session, workspace_id, captured
            )

    rendered = body_md
    for kind in _CITATION_KINDS:
        hits = hits_per_kind[kind.key]
        rendered = kind.regex.sub(
            lambda match, _hits=hits, _render=kind.render: _render(
                match, _hits
            ),
            rendered,
        )
    return rendered


__all__: list[str] = [
    "CitationKind",
    "register_citation_kind",
    "registered_citation_kinds",
    "resolve_citations",
]
