"""Cross-entity citations.

Renders ``#dp:cat.schema`` / ``#topic:slug`` / ``#user:email`` /
``#agent:slug`` tokens inside a markdown body into HTML anchors.
Validation runs at *render* time, not at POST time — a citation
to a deleted entity gracefully degrades to literal text.

The refactor lifts the four hand-rolled regex /
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
from typing import Any, cast

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


def _resolve_dp(session: Session, workspace_id: int, pairs: set[Any]) -> set[tuple[str, str]]:
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


def _render_dp(match: re.Match[str], hits: set[tuple[str, str]]) -> str:
    """Build the anchor for ``#dp:cat.sch`` or pass through."""
    catalog, schema = match.group(1), match.group(2)
    if (catalog, schema) not in hits:
        return match.group(0)
    return f"[#{catalog}.{schema}](/data-products/{catalog}/{schema})"


_TOPIC_CITE_RE = re.compile(r"#topic:([a-z0-9][a-z0-9-]{1,60})")


def _resolve_topic(session: Session, workspace_id: int, slugs: set[Any]) -> set[str]:
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
        select(User.id, User.email, User.display_name).where(User.email.in_(emails))
    ).all()
    return {str(email): (int(uid), display_name) for uid, email, display_name in rows}


def _render_user(match: re.Match[str], hits: dict[str, tuple[int, str | None]]) -> str:
    """Build the anchor for ``#user:email`` or pass through."""
    email = match.group(1)
    hit = hits.get(email)
    if hit is None:
        return match.group(0)
    user_id, display_name = hit
    label = display_name or email
    return f"[@{label}](/users/{user_id})"


_AGENT_CITE_RE = re.compile(r"#agent:([a-z0-9][a-z0-9-]{1,60})")


def _resolve_agent(session: Session, workspace_id: int, slugs: set[Any]) -> set[str]:
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


# UC table citations (``#table:cat.sch.tbl``).  No
# existence check against the UC backend in this iteration — the
# resolver accepts every well-formed triple and emits a link via
# the entity registry.  A later sub-phase may add a backend probe
# once soyuz exposes a low-cost ``table exists?`` endpoint.
_TABLE_CITE_RE = re.compile(r"#table:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")


def _resolve_table(
    session: Session, workspace_id: int, triples: set[Any]
) -> set[tuple[str, str, str]]:
    """Pass every well-formed triple through (no UC probe in 77.1).

    Args:
        session: Active SQLAlchemy session (unused — present so the
            signature matches every other resolver).
        workspace_id: Tenant scope (unused for table refs today).
        triples: Set of ``(catalog, schema, table)`` capture tuples.

    Returns:
        The same set the resolver received — all triples are
        treated as "hits" and rendered as anchors.
    """
    del session, workspace_id
    hits: set[tuple[str, str, str]] = set()
    for raw in triples:
        if not isinstance(raw, tuple):
            continue
        parts = cast(tuple[Any, ...], raw)
        if len(parts) != 3:
            continue
        c, s, t = parts
        if isinstance(c, str) and isinstance(s, str) and isinstance(t, str):
            hits.add((c, s, t))
    return hits


def _render_table(match: re.Match[str], hits: set[tuple[str, str, str]]) -> str:
    """Build the anchor for ``#table:cat.sch.tbl`` or pass through."""
    catalog, schema, table = match.group(1), match.group(2), match.group(3)
    if (catalog, schema, table) not in hits:
        return match.group(0)
    return f"[#{catalog}.{schema}.{table}](/catalogs/{catalog}/schemas/{schema}/tables/{table})"


# registered-model citations (``#model:cat.sch.name``).
# Mirrors the table resolver — every well-formed triple becomes an
# anchor; existence-against-MLflow is deferred (the model registry
# does not have a low-cost "exists?" probe that's worth the request
# count for a comment-render path).
_MODEL_CITE_RE = re.compile(r"#model:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")


def _resolve_model(
    session: Session, workspace_id: int, triples: set[Any]
) -> set[tuple[str, str, str]]:
    """Pass every well-formed model triple through (no MLflow probe).

    Args:
        session: Active SQLAlchemy session (unused — present so the
            signature matches every other resolver).
        workspace_id: Tenant scope (unused for model refs today —
            model full_names are globally unique inside their UC
            backend).
        triples: Set of ``(catalog, schema, name)`` capture tuples.

    Returns:
        The same set the resolver received — all triples are
        treated as "hits" and rendered as anchors.
    """
    del session, workspace_id
    hits: set[tuple[str, str, str]] = set()
    for raw in triples:
        if not isinstance(raw, tuple):
            continue
        parts = cast(tuple[Any, ...], raw)
        if len(parts) != 3:
            continue
        c, s, n = parts
        if isinstance(c, str) and isinstance(s, str) and isinstance(n, str):
            hits.add((c, s, n))
    return hits


def _render_model(match: re.Match[str], hits: set[tuple[str, str, str]]) -> str:
    """Build the anchor for ``#model:cat.sch.name`` or pass through."""
    catalog, schema, name = match.group(1), match.group(2), match.group(3)
    if (catalog, schema, name) not in hits:
        return match.group(0)
    return f"[#{catalog}.{schema}.{name}](/models/{catalog}.{schema}.{name})"


# agent-run citations (``#run:<uuid>``).  Matches the
# canonical 36-char UUID shape used by ``agent_runs.id``.  Pass-
# through resolver: every well-formed UUID is treated as a hit and
# rendered as an anchor, falling back to literal text only when the
# regex doesn't match.  A future sub-phase may probe ``agent_runs``
# for existence once the cost is justified.
_RUN_CITE_RE = re.compile(
    r"#run:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def _resolve_run(session: Session, workspace_id: int, uuids: set[Any]) -> set[str]:
    """Pass every well-formed run UUID through (no existence probe).

    Args:
        session: Active SQLAlchemy session (unused — present so the
            signature matches every other resolver).
        workspace_id: Tenant scope (unused for run refs today —
            ``agent_runs.id`` is globally unique).
        uuids: Set of captured UUID strings.

    Returns:
        The same set the resolver received (after dropping any
        non-string entries).
    """
    del session, workspace_id
    return {u for u in uuids if isinstance(u, str)}


def _render_run(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#run:<uuid>`` or pass through."""
    run_id = match.group(1)
    if run_id not in hits:
        return match.group(0)
    short = run_id[:8]
    return f"[#run:{short}](/runs/{run_id})"


# issue citations (``#issue:42``).  Resolver passes every
# well-formed integer-id through (no DB existence probe in this
# iteration — the typical comment body rarely cites issue ids that
# don't exist, and the literal-fallback render path is harmless).
_ISSUE_CITE_RE = re.compile(r"#issue:(\d{1,9})")


def _resolve_issue(session: Session, workspace_id: int, ids: set[Any]) -> set[str]:
    """Pass every well-formed issue-id string through (no existence probe).

    Args:
        session: Active SQLAlchemy session (unused — present so the
            signature matches every other resolver).
        workspace_id: Tenant scope (unused for issue refs today).
        ids: Set of captured digit strings.

    Returns:
        The same set the resolver received after filtering to strings.
    """
    del session, workspace_id
    return {i for i in ids if isinstance(i, str)}


def _render_issue(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#issue:42`` or pass through."""
    issue_id = match.group(1)
    if issue_id not in hits:
        return match.group(0)
    return f"[#issue:{issue_id}](/issues/{issue_id})"


# schema citations (``#schema:cat.sch``).  Pass-through
# resolver — UC backend existence checks are skipped because soyuz
# may be offline during comment renders (catalog-browser pages must
# stay responsive even when the backend is slow).
_SCHEMA_CITE_RE = re.compile(r"#schema:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")


def _resolve_schema(session: Session, workspace_id: int, pairs: set[Any]) -> set[tuple[str, str]]:
    """Pass every well-formed ``(catalog, schema)`` pair through.

    Args:
        session: Active SQLAlchemy session (unused — present so the
            signature matches every other resolver).
        workspace_id: Tenant scope (unused — UC schemas live under
            catalog pins resolved separately).
        pairs: Set of ``(catalog, schema)`` capture tuples.

    Returns:
        The same set the resolver received after dropping any
        malformed tuples.
    """
    del session, workspace_id
    hits: set[tuple[str, str]] = set()
    for raw in pairs:
        if not isinstance(raw, tuple):
            continue
        parts = cast(tuple[Any, ...], raw)
        if len(parts) != 2:
            continue
        c, s = parts
        if isinstance(c, str) and isinstance(s, str):
            hits.add((c, s))
    return hits


def _render_schema(match: re.Match[str], hits: set[tuple[str, str]]) -> str:
    """Build the anchor for ``#schema:cat.sch`` or pass through."""
    catalog, schema = match.group(1), match.group(2)
    if (catalog, schema) not in hits:
        return match.group(0)
    return f"[#{catalog}.{schema}](/catalogs/{catalog}/schemas/{schema})"


# catalog citations (``#catalog:name``).  Same pass-
# through pattern as schemas; the resolver mirrors them so a single
# render pass picks up both kinds.
_CATALOG_CITE_RE = re.compile(r"#catalog:([A-Za-z0-9_]+)")


def _resolve_catalog(session: Session, workspace_id: int, names: set[Any]) -> set[str]:
    """Pass every well-formed catalog name through."""
    del session, workspace_id
    return {n for n in names if isinstance(n, str)}


def _render_catalog(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#catalog:name`` or pass through."""
    name = match.group(1)
    if name not in hits:
        return match.group(0)
    return f"[#{name}](/catalogs/{name})"


# notebook citations (``#notebook:<uuid>``).  Matches
# the canonical 36-char UUID shape used by ``notebooks.id``.
_NOTEBOOK_CITE_RE = re.compile(
    r"#notebook:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def _resolve_notebook(session: Session, workspace_id: int, uuids: set[Any]) -> set[str]:
    """Pass every well-formed notebook UUID through."""
    del session, workspace_id
    return {u for u in uuids if isinstance(u, str)}


def _render_notebook(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#notebook:<uuid>`` or pass through."""
    nb_id = match.group(1)
    if nb_id not in hits:
        return match.group(0)
    short = nb_id[:8]
    return f"[#notebook:{short}](/notebooks/uuid/{nb_id})"


# saved-query citations (``#query:slug``).  The slug
# regex mirrors ``#topic:`` — lowercase alphanumerics + hyphens.
_QUERY_CITE_RE = re.compile(r"#query:([a-z0-9][a-z0-9-]{1,60})")


def _resolve_query(session: Session, workspace_id: int, slugs: set[Any]) -> set[str]:
    """Pass every well-formed query slug through (no existence probe)."""
    del session, workspace_id
    return {s for s in slugs if isinstance(s, str)}


def _render_query(match: re.Match[str], hits: set[str]) -> str:
    """Build the anchor for ``#query:slug`` or pass through."""
    slug = match.group(1)
    if slug not in hits:
        return match.group(0)
    return f"[#{slug}](/audit/queries/{slug})"


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
    CitationKind(
        key="table",
        regex=_TABLE_CITE_RE,
        resolve=_resolve_table,
        render=_render_table,
    ),
    CitationKind(
        key="model",
        regex=_MODEL_CITE_RE,
        resolve=_resolve_model,
        render=_render_model,
    ),
    CitationKind(
        key="run",
        regex=_RUN_CITE_RE,
        resolve=_resolve_run,
        render=_render_run,
    ),
    CitationKind(
        key="issue",
        regex=_ISSUE_CITE_RE,
        resolve=_resolve_issue,
        render=_render_issue,
    ),
    CitationKind(
        key="schema",
        regex=_SCHEMA_CITE_RE,
        resolve=_resolve_schema,
        render=_render_schema,
    ),
    CitationKind(
        key="catalog",
        regex=_CATALOG_CITE_RE,
        resolve=_resolve_catalog,
        render=_render_catalog,
    ),
    CitationKind(
        key="notebook",
        regex=_NOTEBOOK_CITE_RE,
        resolve=_resolve_notebook,
        render=_render_notebook,
    ),
    CitationKind(
        key="saved_query",
        regex=_QUERY_CITE_RE,
        resolve=_resolve_query,
        render=_render_query,
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
            captured = {m if isinstance(m, str) else tuple(m) for m in kind.regex.findall(body_md)}
            hits_per_kind[kind.key] = kind.resolve(session, workspace_id, captured)

    rendered = body_md
    for kind in _CITATION_KINDS:
        hits = hits_per_kind[kind.key]
        rendered = kind.regex.sub(
            lambda match, _hits=hits, _render=kind.render: _render(match, _hits),
            rendered,
        )
    return rendered


__all__: list[str] = [
    "CitationKind",
    "register_citation_kind",
    "registered_citation_kinds",
    "resolve_citations",
]
