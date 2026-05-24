"""Slug helpers for the topics surface."""

from __future__ import annotations

import re

_SLUG_NORMALISE_RE = re.compile(r"[^a-z0-9]+")


def slugify(display_name: str) -> str:
    """Lowercase + collapse non-alphanumeric runs into single hyphens.

    Args:
        display_name: The human-friendly label.

    Returns:
        A URL-safe slug ≤ 60 chars long, never starting or ending
        with a hyphen.  Empty input maps to ``"topic"`` so the
        unique-slug check downstream always has something to
        compare against.
    """
    lowered = display_name.strip().lower()
    slug = _SLUG_NORMALISE_RE.sub("-", lowered).strip("-")
    if not slug:
        return "topic"
    return slug[:60]
