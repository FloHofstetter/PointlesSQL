"""Cross-DP / cross-user / cross-topic citations (Phase 76.6).

Renders ``#dp:cat.schema`` / ``#topic:slug`` / ``#user:email`` /
``#agent:slug`` tokens inside a markdown body into HTML anchors.
Validation runs at *render* time, not at POST time — a citation
to a deleted entity gracefully degrades to literal text.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._topic import Topic

_DP_CITE_RE = re.compile(r"#dp:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")
_TOPIC_CITE_RE = re.compile(r"#topic:([a-z0-9][a-z0-9-]{1,60})")
_USER_CITE_RE = re.compile(r"#user:([\w.+-]+@[\w-]+\.[\w.-]+)")
_AGENT_CITE_RE = re.compile(r"#agent:([a-z0-9][a-z0-9-]{1,60})")


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
        workspace_id: Tenant scope used to filter the four
            resolution lookups.

    Returns:
        A string with every resolvable cite token replaced by
        ``[label](href)`` (markdown anchor).  Unresolvable tokens
        stay literal.
    """
    if not body_md or "#" not in body_md:
        return body_md

    with session_factory() as session:
        dp_pairs = set(_DP_CITE_RE.findall(body_md))
        topic_slugs = set(_TOPIC_CITE_RE.findall(body_md))
        user_emails = set(_USER_CITE_RE.findall(body_md))
        agent_slugs = set(_AGENT_CITE_RE.findall(body_md))

        dp_hits: set[tuple[str, str]] = set()
        if dp_pairs:
            rows = (
                session.execute(
                    select(DataProduct.catalog_name, DataProduct.schema_name).where(
                        DataProduct.workspace_id == workspace_id,
                    )
                )
                .all()
            )
            present = {(c, s) for c, s in rows}
            dp_hits = present & dp_pairs

        topic_hits: set[str] = set()
        if topic_slugs:
            rows = (
                session.execute(
                    select(Topic.slug).where(
                        Topic.workspace_id == workspace_id,
                        Topic.slug.in_(topic_slugs),
                    )
                )
                .all()
            )
            topic_hits = {s for (s,) in rows}

        user_hits: dict[str, tuple[int, str | None]] = {}
        if user_emails:
            rows = (
                session.execute(
                    select(User.id, User.email, User.display_name).where(
                        User.email.in_(user_emails)
                    )
                )
                .all()
            )
            user_hits = {
                str(email): (int(uid), display_name)
                for uid, email, display_name in rows
            }

        agent_hits: set[str] = set()
        if agent_slugs:
            rows = (
                session.execute(
                    select(Agent.slug).where(
                        Agent.workspace_id == workspace_id,
                        Agent.slug.in_(agent_slugs),
                    )
                )
                .all()
            )
            agent_hits = {s for (s,) in rows}

    def _replace_dp(match: re.Match[str]) -> str:
        catalog, schema = match.group(1), match.group(2)
        if (catalog, schema) not in dp_hits:
            return match.group(0)
        return f"[#{catalog}.{schema}](/data-products/{catalog}/{schema})"

    def _replace_topic(match: re.Match[str]) -> str:
        slug = match.group(1)
        if slug not in topic_hits:
            return match.group(0)
        return f"[#{slug}](/topics/{slug})"

    def _replace_user(match: re.Match[str]) -> str:
        email = match.group(1)
        hit = user_hits.get(email)
        if hit is None:
            return match.group(0)
        user_id, display_name = hit
        label = display_name or email
        return f"[@{label}](/users/{user_id})"

    def _replace_agent(match: re.Match[str]) -> str:
        slug = match.group(1)
        if slug not in agent_hits:
            return match.group(0)
        return f"[@{slug}](/agents/{slug})"

    body_md = _DP_CITE_RE.sub(_replace_dp, body_md)
    body_md = _TOPIC_CITE_RE.sub(_replace_topic, body_md)
    body_md = _USER_CITE_RE.sub(_replace_user, body_md)
    body_md = _AGENT_CITE_RE.sub(_replace_agent, body_md)
    return body_md
