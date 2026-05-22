"""@-mention extraction + database resolution for comment bodies.

Two mention forms are supported:

* ``@<email>`` — uniquely identifies a user.  Resolved
  case-insensitively against the ``users`` table.
* ``@<display_name>`` — resolves only when exactly one user
  carries that display name (case-insensitively).  Ambiguous
  tokens are reported back so an ``audit.discussion.mention_ambiguous``
  row can be written.

Fenced ```...``` blocks are stripped before scanning so a
documentation example doesn't spam a real user.  Inline ``code``
is *not* stripped — too aggressive for one regex, documented as a
known limitation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from pointlessql.api.data_products_routes.comments._constants import (
    DISPLAYNAME_MENTION_RE,
    FENCED_CODE_RE,
    MENTION_RE,
)
from pointlessql.models.auth import User


def extract_mention_emails(body_md: str) -> list[str]:
    """Return ``@email`` mentions in *body_md* with fenced code stripped."""
    stripped = FENCED_CODE_RE.sub("", body_md)
    return MENTION_RE.findall(stripped)


def extract_displayname_mentions(body_md: str) -> list[str]:
    """Return ``@display_name`` mentions, fenced-code-aware.

    The email-pattern matches first; we de-duplicate by stripping
    any token containing ``@`` post-scan so a single ``@alice@x.y``
    isn't double-counted.
    """
    stripped = FENCED_CODE_RE.sub("", body_md)
    raw = DISPLAYNAME_MENTION_RE.findall(stripped)
    return [t for t in raw if "@" not in t]


def resolve_mentions(session: Any, emails: list[str]) -> list[int]:
    """Map @-mention emails to their persisted user ids (case-insensitive)."""
    if not emails:
        return []
    lowered = list({e.lower() for e in emails})
    users = (
        session.execute(
            select(User.id, User.email).where(User.email.in_(lowered))
        ).all()
    )
    return [int(uid) for uid, _email in users]


def resolve_displayname_mentions(
    session: Any, tokens: list[str]
) -> tuple[list[int], list[str]]:
    """Map ``@display_name`` mentions to user ids with disambiguation.

    Two users sharing the same ``display_name`` are unresolvable —
    we skip both (callers can fall back to ``@email`` for
    precision) and surface the ambiguous token to the caller so
    an audit row can be written.

    Args:
        session: Open SQLAlchemy session.
        tokens: De-duplicated display-name fragments extracted from
            the comment body.

    Returns:
        ``(resolved_user_ids, ambiguous_tokens)``.  ``resolved`` is
        empty when no token matched exactly one user.
    """
    if not tokens:
        return [], []
    lowered = list({t.lower() for t in tokens})
    rows = (
        session.execute(
            select(User.id, User.display_name).where(
                func.lower(User.display_name).in_(lowered)
            )
        ).all()
    )
    by_name: dict[str, list[int]] = {}
    for uid, name in rows:
        by_name.setdefault(name.lower(), []).append(int(uid))
    resolved: list[int] = []
    ambiguous: list[str] = []
    for token in lowered:
        hits = by_name.get(token, [])
        if len(hits) == 1:
            resolved.append(hits[0])
        elif len(hits) > 1:
            ambiguous.append(token)
    return resolved, ambiguous
