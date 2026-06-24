"""The soyuz client is built with bounded HTTP timeouts.

The generated client defaults to no timeout, so a hung soyuz endpoint
would pin the calling worker forever.  These tests pin that both factory
functions attach the configured ``httpx.Timeout``.
"""

from __future__ import annotations

from pointlessql.config import Settings
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client


def test_make_soyuz_client_has_bounded_read_timeout() -> None:
    """The default client carries a finite read timeout, not None."""
    client = make_soyuz_client(Settings())
    timeout = client.get_async_httpx_client().timeout
    assert timeout.read == 30.0
    assert timeout.connect == 5.0


def test_make_principal_client_has_bounded_read_timeout() -> None:
    """The per-principal client carries the same bounded timeout."""
    client = make_principal_client(Settings(), "user@test.com")
    timeout = client.get_async_httpx_client().timeout
    assert timeout.read == 30.0
    assert timeout.write == 10.0
