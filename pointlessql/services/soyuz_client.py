"""Factory for a configured soyuz-catalog client instance."""

from __future__ import annotations

import httpx
from soyuz_catalog_client import Client

from pointlessql.config import (
    Settings,
    correlation_id_var,
    get_settings,
    request_id_var,
)

# Context-var values that mean "no real id" — the logging filter renders an
# unset id as ``-``; never forward that as if it were a trace id.
_TRACE_SENTINELS = frozenset({"", "-"})


def _trace_headers() -> dict[str, str]:
    """Build correlation/request-id headers from the active log context.

    Forwards the in-flight request's identifiers so soyuz-catalog can link
    the HTTP hop into the same trace instead of starting a fresh one. soyuz
    honours an inbound ``X-Request-ID`` (it coerces the value to a UUID and
    echoes it back), so that header is what actually stitches the two
    services' logs together; ``X-Correlation-ID`` rides along carrying the
    logical-task id that may span several requests. Unset / sentinel values
    are skipped so a non-request caller (startup, a background tick) sends
    no misleading id.

    Returns:
        The header dict to merge into a client's headers; empty when called
        outside any request scope.
    """
    headers: dict[str, str] = {}
    request_id = request_id_var.get()
    if request_id and request_id not in _TRACE_SENTINELS:
        headers["X-Request-ID"] = request_id
    correlation_id = correlation_id_var.get() or request_id
    if correlation_id and correlation_id not in _TRACE_SENTINELS:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def _soyuz_timeout(settings: Settings) -> httpx.Timeout:
    """Build the bounded HTTP timeout for soyuz calls from settings.

    Args:
        settings: Application settings carrying the per-phase timeouts.

    Returns:
        An ``httpx.Timeout`` so a hung soyuz endpoint cannot pin a worker.
    """
    soyuz = settings.soyuz
    return httpx.Timeout(
        connect=soyuz.connect_timeout_seconds,
        read=soyuz.read_timeout_seconds,
        write=soyuz.write_timeout_seconds,
        pool=soyuz.pool_timeout_seconds,
    )


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
    settings = settings or get_settings()
    headers: dict[str, str] = _trace_headers()
    if agent_run_id:
        headers["X-Agent-Run-Id"] = agent_run_id
    return Client(
        base_url=settings.soyuz.catalog_url,
        raise_on_unexpected_status=True,
        headers=headers,
        timeout=_soyuz_timeout(settings),
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
    headers = {"X-Principal": principal, **_trace_headers()}
    if agent_run_id:
        headers["X-Agent-Run-Id"] = agent_run_id
    return Client(
        base_url=settings.soyuz.catalog_url,
        raise_on_unexpected_status=True,
        headers=headers,
        timeout=_soyuz_timeout(settings),
    )
