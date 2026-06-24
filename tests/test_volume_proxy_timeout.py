"""Volume proxy clients use a generous, bounded transfer timeout.

The upload/download proxies inherited httpx's 5s default, too short for
large file bodies and unbounded on a wedged backend.  This pins the
proxy_timeout helper the routes build their clients from.
"""

from __future__ import annotations

from pointlessql.config import Settings
from pointlessql.services.volumes import proxy_timeout


def test_proxy_timeout_reads_setting() -> None:
    """read/write follow the configured budget; connect/pool stay tight."""
    timeout = proxy_timeout(Settings())
    assert timeout.read == 60.0
    assert timeout.write == 60.0
    assert timeout.connect == 5.0
    assert timeout.pool == 5.0


def test_proxy_timeout_honours_override() -> None:
    """A configured value flows through to the timeout."""
    settings = Settings()
    settings.soyuz.volume_proxy_timeout_seconds = 120.0
    assert proxy_timeout(settings).read == 120.0
