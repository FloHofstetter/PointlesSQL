"""Mutation-killing tests for the object-store storage-options resolver.

Exact-value assertions over every branch of the pure helpers and the
:class:`VendingResolver` internals, so a flipped comparison, a tweaked
constant, or a dropped connection-param is observable. Companion to the
behavioural tests in ``test_pql_storage_options.py`` /
``test_pql_vending_resolver.py``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from soyuz_catalog_client.models.aws_credentials import AwsCredentials
from soyuz_catalog_client.models.temporary_credentials import TemporaryCredentials

from pointlessql.config import GCSSettings, ObjectStoreSettings, S3Settings
from pointlessql.pql import _storage_options as so
from pointlessql.pql._storage_options import (
    VendingResolver,
    _bucket_key,
    _expiry_seconds,
    _real_aws_credentials,
    build_gcs_storage_options,
)

_FUTURE_MS = int((time.time() + 3600) * 1000)


def _resolver(**s3: Any) -> VendingResolver:
    return VendingResolver(object(), ObjectStoreSettings(s3=S3Settings(**s3)))


def _no_call(*_: Any, **__: Any) -> Any:
    raise AssertionError("fetch_path_credentials must not be called here")


class TestBuildGcs:
    """Every GCS field maps to its exact delta-rs key."""

    def test_empty(self) -> None:
        assert build_gcs_storage_options(GCSSettings()) == {}

    def test_service_account_path(self) -> None:
        opts = build_gcs_storage_options(GCSSettings(service_account_path=Path("/k/sa.json")))
        assert opts == {"GOOGLE_SERVICE_ACCOUNT": "/k/sa.json"}

    def test_service_account_key(self) -> None:
        opts = build_gcs_storage_options(GCSSettings(service_account_key="{json}"))
        assert opts == {"GOOGLE_SERVICE_ACCOUNT_KEY": "{json}"}

    def test_bearer_token(self) -> None:
        opts = build_gcs_storage_options(GCSSettings(bearer_token="tok"))
        assert opts == {"GOOGLE_BEARER_TOKEN": "tok"}

    def test_all_three(self) -> None:
        opts = build_gcs_storage_options(
            GCSSettings(
                service_account_path=Path("/k/sa.json"),
                service_account_key="{json}",
                bearer_token="tok",
            )
        )
        assert opts == {
            "GOOGLE_SERVICE_ACCOUNT": "/k/sa.json",
            "GOOGLE_SERVICE_ACCOUNT_KEY": "{json}",
            "GOOGLE_BEARER_TOKEN": "tok",
        }


class TestBucketKey:
    """The cache key is exactly ``scheme://netloc``."""

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            ("s3://bucket/a/b/c", "s3://bucket"),
            ("s3://bucket", "s3://bucket"),
            ("abfss://c@acct.dfs.core.windows.net/p", "abfss://c@acct.dfs.core.windows.net"),
            ("gs://gbucket/x", "gs://gbucket"),
        ],
    )
    def test_bucket_key(self, location: str, expected: str) -> None:
        assert _bucket_key(location) == expected


class TestExpirySeconds:
    """The cache-until arithmetic is pinned to exact values."""

    def test_none_credentials(self) -> None:
        assert _expiry_seconds(None, 1000.0, 60.0) == 1060.0

    def test_no_expiration_field(self) -> None:
        assert _expiry_seconds(TemporaryCredentials(), 1000.0, 60.0) == 1060.0

    def test_zero_expiration(self) -> None:
        assert _expiry_seconds(TemporaryCredentials(expiration_time=0), 1000.0, 60.0) == 1060.0

    def test_future_expiration_is_minute_before(self) -> None:
        # 2_000_000 ms -> 2000 s; 2000 - 60 = 1940; now 1000 < 1940 -> 1940.
        cred = TemporaryCredentials(expiration_time=2_000_000)
        assert _expiry_seconds(cred, 1000.0, 60.0) == 1940.0

    def test_past_expiration_clamped_to_now(self) -> None:
        # 100_000 ms -> 100 s; 100 - 60 = 40; max(now 1000, 40) -> 1000.
        cred = TemporaryCredentials(expiration_time=100_000)
        assert _expiry_seconds(cred, 1000.0, 60.0) == 1000.0


class TestRealAwsCredentials:
    """Only a populated ``AwsCredentials`` counts as real."""

    def test_none(self) -> None:
        assert _real_aws_credentials(None) is None

    def test_unset_aws(self) -> None:
        assert _real_aws_credentials(TemporaryCredentials()) is None

    def test_empty_aws(self) -> None:
        creds = TemporaryCredentials(aws_temp_credentials=AwsCredentials())
        assert _real_aws_credentials(creds) is None

    def test_empty_access_key(self) -> None:
        creds = TemporaryCredentials(aws_temp_credentials=AwsCredentials(access_key_id=""))
        assert _real_aws_credentials(creds) is None

    def test_real_returns_same_object(self) -> None:
        aws = AwsCredentials(access_key_id="AK")
        assert _real_aws_credentials(TemporaryCredentials(aws_temp_credentials=aws)) is aws


class TestS3Options:
    """Connection params + vended keys merge into the exact dict."""

    def test_all_params_and_keys(self) -> None:
        r = _resolver(
            region="eu", endpoint_url="http://e", allow_http=True, allow_unsafe_rename=True
        )
        opts = r._s3_options(
            AwsCredentials(access_key_id="AK", secret_access_key="SK", session_token="TOK")
        )
        assert opts == {
            "AWS_REGION": "eu",
            "AWS_ENDPOINT_URL": "http://e",
            "AWS_ALLOW_HTTP": "true",
            "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
            "AWS_ACCESS_KEY_ID": "AK",
            "AWS_SECRET_ACCESS_KEY": "SK",
            "AWS_SESSION_TOKEN": "TOK",
        }

    def test_region_only_default(self) -> None:
        r = _resolver()  # region default us-east-1, no endpoint/http
        opts = r._s3_options(AwsCredentials(access_key_id="AK", secret_access_key="SK"))
        assert opts == {
            "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "AK",
            "AWS_SECRET_ACCESS_KEY": "SK",
        }

    def test_access_key_only(self) -> None:
        r = _resolver(region="")  # nothing optional set
        opts = r._s3_options(AwsCredentials(access_key_id="AK"))
        assert opts == {"AWS_ACCESS_KEY_ID": "AK"}


class TestRefresh:
    """``_refresh`` returns the right ``(options, expires_at)`` per branch."""

    def test_non_s3_scheme_is_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(so, "fetch_path_credentials", _no_call)
        opts, expires = _resolver()._refresh("abfss://c@a/p", "abfss", 1000.0)
        assert opts is None
        assert expires == 1060.0

    def test_s3_fetch_none_is_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(so, "fetch_path_credentials", lambda _c, _u: None)
        opts, expires = _resolver()._refresh("s3://b/k", "s3", 1000.0)
        assert opts is None
        assert expires == 1060.0

    def test_s3_empty_stub_is_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = TemporaryCredentials(
            aws_temp_credentials=AwsCredentials(), expiration_time=2_000_000
        )
        monkeypatch.setattr(so, "fetch_path_credentials", lambda _c, _u: stub)
        opts, expires = _resolver()._refresh("s3://b/k", "s3", 1000.0)
        assert opts is None
        assert expires == 1060.0

    def test_s3_real_returns_options_and_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cred = TemporaryCredentials(
            aws_temp_credentials=AwsCredentials(access_key_id="AK", secret_access_key="SK"),
            expiration_time=2_000_000,
        )
        monkeypatch.setattr(so, "fetch_path_credentials", lambda _c, _u: cred)
        opts, expires = _resolver(region="eu")._refresh("s3://b/k", "s3", 1000.0)
        assert opts == {
            "AWS_REGION": "eu",
            "AWS_ACCESS_KEY_ID": "AK",
            "AWS_SECRET_ACCESS_KEY": "SK",
        }
        assert expires == 1940.0

    def test_s3_fetch_error_is_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_c: Any, _u: Any) -> Any:
            raise RuntimeError("catalog down")

        monkeypatch.setattr(so, "fetch_path_credentials", _boom)
        opts, expires = _resolver()._refresh("s3://b/k", "s3", 1000.0)
        assert opts is None
        assert expires == 1060.0


class TestResolveCaching:
    """Cache hit returns a copy; a stale entry triggers a re-fetch."""

    def test_local_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(so, "fetch_path_credentials", _no_call)
        assert _resolver().resolve("file:///tmp/x") == {}
        assert _resolver().resolve("/tmp/x") == {}

    def test_positive_result_is_a_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cred = TemporaryCredentials(
            aws_temp_credentials=AwsCredentials(access_key_id="AK", secret_access_key="SK"),
            expiration_time=_FUTURE_MS,
        )
        monkeypatch.setattr(so, "fetch_path_credentials", lambda _c, _u: cred)
        r = _resolver()
        first = r.resolve("s3://bucket/k")
        first["AWS_ACCESS_KEY_ID"] = "MUTATED"
        second = r.resolve("s3://bucket/k")
        assert second["AWS_ACCESS_KEY_ID"] == "AK"

    def test_expired_negative_entry_refetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _count(_c: Any, _u: Any) -> Any:
            calls["n"] += 1
            return None

        monkeypatch.setattr(so, "fetch_path_credentials", _count)
        r = VendingResolver(
            object(), ObjectStoreSettings(s3=S3Settings()), negative_ttl_seconds=0.0
        )
        r.resolve("s3://bucket/k")
        r.resolve("s3://bucket/k")
        assert calls["n"] == 2

    def test_per_bucket_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Different buckets get different vended keys (cache key is per-bucket)."""

        def _fetch(_client: Any, url: str) -> Any:
            bucket = urlparse(url).netloc
            return TemporaryCredentials(
                aws_temp_credentials=AwsCredentials(
                    access_key_id=f"{bucket}-AK", secret_access_key="SK"
                ),
                expiration_time=_FUTURE_MS,
            )

        monkeypatch.setattr(so, "fetch_path_credentials", _fetch)
        r = _resolver()
        first = r.resolve("s3://bucketA/x")
        second = r.resolve("s3://bucketB/y")
        assert first["AWS_ACCESS_KEY_ID"] == "bucketA-AK"
        assert second["AWS_ACCESS_KEY_ID"] == "bucketB-AK"

    def test_client_and_url_are_passed_to_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_refresh`` forwards the real client and the real url to the fetch."""
        sentinel = object()
        seen: dict[str, Any] = {}

        def _fetch(client: Any, url: str) -> Any:
            seen["client"] = client
            seen["url"] = url
            return None

        monkeypatch.setattr(so, "fetch_path_credentials", _fetch)
        VendingResolver(sentinel, ObjectStoreSettings(s3=S3Settings()))._refresh(
            "s3://bucket/k", "s3", 1000.0
        )
        assert seen["client"] is sentinel
        assert seen["url"] == "s3://bucket/k"

    def test_cache_refreshes_at_exact_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``now >= expires`` (not ``>``): a hit exactly at the boundary re-fetches."""
        import types

        calls = {"n": 0}

        def _count(_c: Any, _u: Any) -> Any:
            calls["n"] += 1
            return None

        monkeypatch.setattr(so, "fetch_path_credentials", _count)
        monkeypatch.setattr(so, "time", types.SimpleNamespace(time=lambda: 5000.0))
        r = _resolver()
        r._cache[_bucket_key("s3://bucket/k")] = (None, 5000.0)
        r.resolve("s3://bucket/k")
        assert calls["n"] == 1


class TestRefreshExtra:
    """Branches of ``_refresh`` the happy-path tests do not pin."""

    def test_real_creds_without_expiration_uses_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cred = TemporaryCredentials(
            aws_temp_credentials=AwsCredentials(access_key_id="AK", secret_access_key="SK")
        )
        monkeypatch.setattr(so, "fetch_path_credentials", lambda _c, _u: cred)
        opts, expires = _resolver()._refresh("s3://b/k", "s3", 1000.0)
        assert opts == {
            "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "AK",
            "AWS_SECRET_ACCESS_KEY": "SK",
        }
        assert expires == 1060.0


class TestS3OptionsEmptyStrings:
    """Empty-string (not Unset) secret / token are omitted, not emitted."""

    def test_empty_secret_and_token_omitted(self) -> None:
        opts = _resolver(region="")._s3_options(
            AwsCredentials(access_key_id="AK", secret_access_key="", session_token="")
        )
        assert opts == {"AWS_ACCESS_KEY_ID": "AK"}


class TestVendingFailureLog:
    """The fallback log preserves its exact message and the traceback."""

    def test_failure_logs_exact_message_with_traceback(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        def _boom(_c: Any, _u: Any) -> Any:
            raise RuntimeError("catalog down")

        monkeypatch.setattr(so, "fetch_path_credentials", _boom)
        with caplog.at_level(logging.DEBUG, logger="pointlessql.pql._storage_options"):
            _resolver()._refresh("s3://bucket/k", "s3", 1000.0)
        records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert records
        record = records[-1]
        assert (
            record.getMessage()
            == "credential vending failed for s3://bucket/k; using static config"
        )
        # A truthy 3-tuple (exc_info=True captured the active exception) —
        # distinct from the ``False`` an ``exc_info=False`` mutation leaves.
        assert record.exc_info
        assert record.exc_info[0] is RuntimeError
