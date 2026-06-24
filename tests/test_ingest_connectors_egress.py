"""The ingest HTTP/S3 connector builders are SSRF-guarded.

DuckDB's httpfs reader fetches arbitrary user URLs server-side and
materialises the response into a table, so an unguarded http/s3 source
is a data-exfiltration / SSRF vector.  These tests enable the egress
guard and pin that internal targets are rejected at build time while a
public target still produces a reader.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest.connectors import (
    _build_http_spec,  # pyright: ignore[reportPrivateUsage]
    _build_s3_spec,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture(autouse=True)
def _egress_on(settings_override: Callable[[str, object], None]) -> None:
    """Enable the egress guard for every test in this module."""
    settings_override("egress.enabled", True)


@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/x.csv", "http://localhost/x.csv", "http://127.0.0.1/x.csv"],
)
def test_http_spec_rejects_internal_targets(url: str) -> None:
    """Metadata / loopback http URLs are rejected before reader build."""
    with pytest.raises(ValidationError):
        _build_http_spec({"url": url}, None)


def test_http_spec_allows_public_target() -> None:
    """A public IP-literal http URL still builds a reader (no DNS)."""
    spec = _build_http_spec({"url": "https://8.8.8.8/data.csv"}, None)
    assert spec.sql.startswith("SELECT * FROM")


def test_s3_spec_rejects_raw_internal_bucket_host() -> None:
    """An s3 URL whose bucket host is a raw internal IP is rejected."""
    with pytest.raises(ValidationError):
        _build_s3_spec({"url": "s3://169.254.169.254/x"}, None)


def test_s3_spec_rejects_non_s3_scheme() -> None:
    """A non-s3 scheme on the s3 builder is rejected."""
    with pytest.raises(ValidationError):
        _build_s3_spec({"url": "http://evil.example/x"}, None)


def test_s3_spec_allows_normal_bucket() -> None:
    """A normal bucket name builds a reader."""
    spec = _build_s3_spec({"url": "s3://my-data-bucket/key.csv"}, None)
    assert spec.sql.startswith("SELECT * FROM")
