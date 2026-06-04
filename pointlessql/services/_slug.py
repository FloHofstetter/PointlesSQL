"""Shared URL-safe slug helper for our own metadata rows.

Saved queries, saved views, and alerts each derive a slug from a
user-entered title the same way — trim, lowercase, collapse
non-alphanumeric runs to hyphens, append a short random suffix for
collision-avoidance.  This is the one implementation they share; the
only per-surface difference is the *fallback* used when the title
sanitises to nothing.
"""

from __future__ import annotations

import re
import secrets

_SLUG_SANITIZER = re.compile(r"[^a-z0-9-]+")

#: Width of the ``slug`` columns these helpers feed (SavedQuery /
#: SavedView / Alert all cap at 200).
MAX_SLUG_LEN = 200


def make_slug(title: str, *, fallback: str = "item") -> str:
    """Derive a URL-safe slug from *title* with a 6-char random suffix.

    Pure transform: trim → lowercase → replace non-alphanumeric runs
    with hyphens → trim trailing hyphens.  A 6-char hex random tail
    then guarantees uniqueness even when two users save items with the
    same title.  The base is truncated so the result never exceeds
    :data:`MAX_SLUG_LEN`.

    Args:
        title: The user-entered title.
        fallback: Base used when *title* is empty or sanitises to
            nothing (e.g. ``"query"``, ``"view"``, ``"alert"``).

    Returns:
        A slug shaped ``"<sanitised-title>-<6 hex chars>"``.
    """
    base = (title or fallback).strip().lower()
    base = _SLUG_SANITIZER.sub("-", base).strip("-")
    if not base:
        base = fallback
    # Reserve 7 chars for the suffix + hyphen.
    max_base = MAX_SLUG_LEN - 7
    if len(base) > max_base:
        base = base[:max_base].rstrip("-")
    return f"{base}-{secrets.token_hex(3)}"
