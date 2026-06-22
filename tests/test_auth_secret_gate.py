"""Startup gate that refuses an insecure JWT signing key in production.

The default ``POINTLESSQL_AUTH_SECRET_KEY`` is a public placeholder so a
fresh checkout boots on loopback with no configuration.  Once the server
binds a reachable address, that placeholder (or any too-short key) would
let anyone forge admin sessions, so :func:`assert_secret_key_safe` must
fail loud.  These tests pin both halves of that contract.
"""

from __future__ import annotations

import pytest

from pointlessql.config import (
    AuthSettings,
    ServerSettings,
    Settings,
    assert_secret_key_safe,
)
from pointlessql.config._settings._auth import (  # pyright: ignore[reportPrivateUsage]
    INSECURE_DEFAULT_SECRET_KEY,
    secret_key_is_insecure,
)

_STRONG_KEY = "s3cret-but-long-enough-to-pass-the-floor"


def _settings(host: str, secret_key: str) -> Settings:
    """Build a root settings object pinned to *host* and *secret_key*.

    Args:
        host: The server bind address to set on ``server.host``.
        secret_key: The JWT signing key to set on ``auth.secret_key``.

    Returns:
        A :class:`Settings` with those two values fixed (the rest at
        their defaults).
    """
    return Settings(
        server=ServerSettings(host=host),
        auth=AuthSettings(secret_key=secret_key),
    )


def test_default_key_on_public_host_is_rejected() -> None:
    """The placeholder key on ``0.0.0.0`` must abort startup."""
    with pytest.raises(RuntimeError, match="POINTLESSQL_AUTH_SECRET_KEY"):
        assert_secret_key_safe(_settings("0.0.0.0", INSECURE_DEFAULT_SECRET_KEY))


def test_short_key_on_public_host_is_rejected() -> None:
    """A too-short custom key on a reachable host is also rejected."""
    with pytest.raises(RuntimeError):
        assert_secret_key_safe(_settings("10.0.0.5", "short"))


def test_strong_key_on_public_host_passes() -> None:
    """A long custom key on a reachable host boots fine."""
    assert_secret_key_safe(_settings("0.0.0.0", _STRONG_KEY))


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_tolerates_default_key(host: str) -> None:
    """Loopback binds keep the zero-config default key usable."""
    assert_secret_key_safe(_settings(host, INSECURE_DEFAULT_SECRET_KEY))


def test_secret_key_is_insecure_predicate() -> None:
    """The low-level predicate flags placeholder/empty/short keys only."""
    assert secret_key_is_insecure(INSECURE_DEFAULT_SECRET_KEY)
    assert secret_key_is_insecure("")
    assert secret_key_is_insecure("fifteen-chars--")
    assert not secret_key_is_insecure(_STRONG_KEY)
