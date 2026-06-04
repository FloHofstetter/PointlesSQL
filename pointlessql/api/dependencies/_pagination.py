"""Bounded offset+limit pagination dependency for list endpoints.

The shared :func:`pagination` dependency replaces the copy-pasted
``Query(default=...)`` declarations that list routes across audit,
runs, data-products, notifications and social used to spell out by
hand.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class PaginationParams:
    """Bounded offset+limit pair for list endpoints.

    Used as the return type of :func:`pagination`, the shared
    FastAPI dependency that replaces 30+ copy-pasted
    ``Query(default=...)`` declarations across audit, runs,
    data-products, notifications and social routes.

    Attributes:
        offset: Row offset (``>= 0``).
        limit: Page size (``1 <= limit <= 1000``).
    """

    offset: int
    limit: int


def pagination(
    offset: int = Query(0, ge=0, description="Row offset (>= 0)."),
    limit: int = Query(100, ge=1, le=1000, description="Page size (1-1000)."),
) -> PaginationParams:
    """Return bounded :class:`PaginationParams` for a list route.

    Args:
        offset: Row offset, validated by FastAPI to be non-negative.
        limit: Page size, validated by FastAPI to be in ``[1, 1000]``.

    Returns:
        A frozen :class:`PaginationParams` carrying the validated pair.
    """
    return PaginationParams(offset=offset, limit=limit)
