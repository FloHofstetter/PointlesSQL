"""Factory for a configured soyuz-catalog client instance."""

from __future__ import annotations

from soyuz_catalog_client import Client

from pointlessql.config import Settings


def make_soyuz_client(
    settings: Settings | None = None,
    *,
    agent_run_id: str | None = None,
) -> Client:
    """Build a soyuz-catalog client from application settings.

    Args:
        settings: Optional override; when *None* a fresh ``Settings``
            instance is created (reading env vars automatically).
        agent_run_id: Optional run-UUID to forward as
            ``X-Agent-Run-Id`` so soyuz's audit log can attribute
            every UC mutation made through this client to the
            owning PointlesSQL run ( cross-reference).

    Returns:
        A ready-to-use ``Client`` pointing at the configured
        soyuz-catalog server.
    """
    settings = settings or Settings()
    headers: dict[str, str] = {}
    if agent_run_id:
        headers["X-Agent-Run-Id"] = agent_run_id
    return Client(
        base_url=settings.soyuz.catalog_url,
        raise_on_unexpected_status=True,
        headers=headers,
    )


def make_principal_client(
    settings: Settings,
    principal: str,
    *,
    agent_run_id: str | None = None,
) -> Client:
    """Build a per-request client with an ``X-Principal`` header.

    Args:
        settings: Application settings (for the soyuz-catalog URL).
        principal: The user email to forward as the acting principal.
        agent_run_id: Optional run-UUID to forward as
            ``X-Agent-Run-Id`` so soyuz's audit log can attribute
            every UC mutation made through this client to the
            owning PointlesSQL run ( cross-reference).

    Returns:
        A ``Client`` instance with the ``X-Principal`` header set
        (and ``X-Agent-Run-Id`` when ``agent_run_id`` is non-empty).
    """
    headers = {"X-Principal": principal}
    if agent_run_id:
        headers["X-Agent-Run-Id"] = agent_run_id
    return Client(
        base_url=settings.soyuz.catalog_url,
        raise_on_unexpected_status=True,
        headers=headers,
    )
