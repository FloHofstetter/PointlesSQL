"""Unit tests for the Unity Catalog credential VendingResolver.

These exercise the resolver's decision logic with the soyuz call
monkeypatched — no live catalog. They pin: real vended S3 keys are
merged with the configured connection params; an empty stub / non-S3
scheme / error falls back to static config; per-bucket caching avoids
re-hitting the catalog.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from soyuz_catalog_client.models.aws_credentials import AwsCredentials
from soyuz_catalog_client.models.temporary_credentials import TemporaryCredentials

from pointlessql.config import AzureSettings, ObjectStoreSettings, S3Settings
from pointlessql.pql import _storage_options
from pointlessql.pql._storage_options import VendingResolver, make_resolver

_FUTURE_MS = int((time.time() + 3600) * 1000)


def _store(**s3: Any) -> ObjectStoreSettings:
    return ObjectStoreSettings(
        s3=S3Settings(**s3),
        azure=AzureSettings(account_name="acct", account_key="key"),
    )


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, response: Any) -> dict[str, int]:
    """Patch the soyuz fetch to return ``response`` and count the calls."""
    calls = {"n": 0}

    def _fake(_client: Any, _url: str) -> Any:
        calls["n"] += 1
        return response

    monkeypatch.setattr(_storage_options, "fetch_path_credentials", _fake)
    return calls


def test_local_path_never_vends(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local path resolves to ``{}`` without touching the catalog."""
    calls = _patch_fetch(monkeypatch, None)
    resolver = VendingResolver(object(), _store())
    assert resolver.resolve("file:///tmp/t") == {}
    assert calls["n"] == 0


def test_real_keys_merged_with_connection_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vended S3 keys combine with endpoint/region/http from config."""
    vended = TemporaryCredentials(
        aws_temp_credentials=AwsCredentials(
            access_key_id="VENDED_AK",
            secret_access_key="VENDED_SK",
            session_token="VENDED_TOK",
        ),
        expiration_time=_FUTURE_MS,
    )
    _patch_fetch(monkeypatch, vended)
    resolver = VendingResolver(
        object(),
        _store(region="eu-west-1", endpoint_url="http://s3:8333", allow_http=True),
    )
    opts = resolver.resolve("s3://bucket/cat/schema/tbl")
    assert opts["AWS_ACCESS_KEY_ID"] == "VENDED_AK"
    assert opts["AWS_SECRET_ACCESS_KEY"] == "VENDED_SK"
    assert opts["AWS_SESSION_TOKEN"] == "VENDED_TOK"
    assert opts["AWS_ENDPOINT_URL"] == "http://s3:8333"
    assert opts["AWS_REGION"] == "eu-west-1"
    assert opts["AWS_ALLOW_HTTP"] == "true"


def test_empty_stub_falls_back_to_static(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty ``aws_temp_credentials`` stub uses the static config keys."""
    stub = TemporaryCredentials(aws_temp_credentials=AwsCredentials(), expiration_time=_FUTURE_MS)
    _patch_fetch(monkeypatch, stub)
    resolver = VendingResolver(object(), _store(access_key_id="STATIC_AK", secret_access_key="s"))
    opts = resolver.resolve("s3://bucket/tbl")
    assert opts["AWS_ACCESS_KEY_ID"] == "STATIC_AK"


def test_non_s3_scheme_uses_static_without_vending(monkeypatch: pytest.MonkeyPatch) -> None:
    """Azure/GCS skip the catalog (soyuz doesn't vend them) and use static."""
    calls = _patch_fetch(monkeypatch, None)
    resolver = VendingResolver(object(), _store())
    opts = resolver.resolve("abfss://c@a.dfs.core.windows.net/p")
    assert opts["AZURE_STORAGE_ACCOUNT_NAME"] == "acct"
    assert calls["n"] == 0


def test_fetch_error_falls_back_to_static(monkeypatch: pytest.MonkeyPatch) -> None:
    """A catalog error degrades to static config, never raises."""

    def _boom(_client: Any, _url: str) -> Any:
        raise RuntimeError("catalog down")

    monkeypatch.setattr(_storage_options, "fetch_path_credentials", _boom)
    resolver = VendingResolver(object(), _store(access_key_id="STATIC_AK", secret_access_key="s"))
    opts = resolver.resolve("s3://bucket/tbl")
    assert opts["AWS_ACCESS_KEY_ID"] == "STATIC_AK"


def test_result_is_cached_per_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two resolves under the same bucket hit the catalog once."""
    vended = TemporaryCredentials(
        aws_temp_credentials=AwsCredentials(access_key_id="AK", secret_access_key="SK"),
        expiration_time=_FUTURE_MS,
    )
    calls = _patch_fetch(monkeypatch, vended)
    resolver = VendingResolver(object(), _store())
    resolver.resolve("s3://bucket/a")
    resolver.resolve("s3://bucket/b")
    assert calls["n"] == 1


def test_make_resolver_returns_vending_with_client() -> None:
    """The factory wires a VendingResolver when a client is present."""
    assert isinstance(make_resolver(_store(), object()), VendingResolver)
