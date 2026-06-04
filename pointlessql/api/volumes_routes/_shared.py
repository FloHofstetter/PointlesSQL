"""Shared helpers for the route package."""

from __future__ import annotations

import logging

from fastapi import Request

from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError

logger = logging.getLogger(__name__)

def soyuz_base_url(request: Request) -> str:
    """Return the configured soyuz-catalog base URL.

    Args:
        request: Incoming request.

    Returns:
        The base URL string (without trailing slash).
    """
    settings: Settings = request.app.state.settings
    return settings.soyuz.catalog_url.rstrip("/")


async def volume_full_name_split(full_name: str) -> tuple[str, str, str]:
    """Split *full_name* into its UC three parts or raise.

    Args:
        full_name: Dotted identifier.

    Returns:
        Tuple ``(catalog, schema, volume)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.volume, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]
