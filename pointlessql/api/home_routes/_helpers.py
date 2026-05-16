"""Scoring + time-normalisation helpers shared across home_routes.

Both ``summary.py`` and ``search.py`` need these so they live in
``_helpers.py`` and stay public (no leading underscore in the
function names — only the module is private to the package).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def score_match(needle: str, haystack: str) -> float | None:
    """Return the match score or ``None`` when *needle* is absent.

    Prefix matches outrank substring matches so that typing ``prod`` ranks
    ``prod_orders`` above ``backup_prod``. Needle is assumed already
    casefolded; haystack is casefolded here so callers can pass raw names.
    """
    if not haystack:
        return None
    hay = haystack.casefold()
    if hay.startswith(needle):
        return 2.0
    if needle in hay:
        return 1.0
    return None


def epoch_seconds(value: Any) -> float:
    """Normalize a soyuz epoch-ms int or ORM ``datetime`` to float seconds.

    Used as the tiebreak key for `/api/search`. ``None`` and unrecognized
    types collapse to ``0.0`` so those hits always lose the tiebreak
    rather than raising mid-sort.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0
