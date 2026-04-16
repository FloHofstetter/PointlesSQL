"""Factory for a configured soyuz-catalog client instance."""

from __future__ import annotations

from soyuz_catalog_client import Client

from pointlessql.settings import Settings


def make_soyuz_client(settings: Settings | None = None) -> Client:
    """Build a soyuz-catalog client from application settings.

    Args:
        settings: Optional override; when *None* a fresh ``Settings``
            instance is created (reading env vars automatically).

    Returns:
        A ready-to-use ``Client`` pointing at the configured
        soyuz-catalog server.
    """
    settings = settings or Settings()
    return Client(
        base_url=settings.soyuz_catalog_url,
        raise_on_unexpected_status=True,
    )
