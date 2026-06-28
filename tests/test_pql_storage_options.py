"""Unit tests for the object-store ``storage_options`` resolver.

These are pure-function tests — no S3 server, no network.  They pin the
mapping from :class:`~pointlessql.config.ObjectStoreSettings` to the
``deltalake`` ``storage_options`` keys, the scheme classification, and
the byte-stable ``{} -> None`` collapse that keeps local Delta calls
identical to the pre-object-storage behaviour.  A live round-trip against
a real S3 endpoint is covered separately by the integration suite.
"""

from __future__ import annotations

import pytest

from pointlessql.config import AzureSettings, GCSSettings, ObjectStoreSettings, S3Settings
from pointlessql.pql._storage_options import (
    NullResolver,
    StaticResolver,
    build_azure_storage_options,
    build_gcs_storage_options,
    build_s3_storage_options,
    is_object_storage,
    make_resolver,
    scheme_of,
    storage_options_for,
)


class TestSchemeClassification:
    """``scheme_of`` / ``is_object_storage`` URI parsing."""

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            ("/tmp/x", ""),
            ("file:///tmp/x", "file"),
            ("s3://bucket/key", "s3"),
            ("S3://Bucket/Key", "s3"),
            ("s3a://bucket/key", "s3a"),
            ("abfss://c@a.dfs.core.windows.net/p", "abfss"),
            ("gs://bucket/key", "gs"),
        ],
    )
    def test_scheme_of(self, location: str, expected: str) -> None:
        """Scheme is lower-cased; a bare path yields the empty string."""
        assert scheme_of(location) == expected

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            ("/tmp/x", False),
            ("file:///tmp/x", False),
            ("s3://b/k", True),
            ("s3a://b/k", True),
            ("abfss://c@a/p", True),
            ("gs://b/k", True),
            ("gcs://b/k", True),
        ],
    )
    def test_is_object_storage(self, location: str, expected: bool) -> None:
        """Only cloud schemes (and aliases) count as object storage."""
        assert is_object_storage(location) is expected


class TestBuildS3:
    """``build_s3_storage_options`` field mapping + the all-default gate."""

    def test_unconfigured_is_empty(self) -> None:
        """An all-default block yields ``{}`` (region alone must not leak)."""
        assert build_s3_storage_options(S3Settings()) == {}

    def test_region_alone_does_not_activate(self) -> None:
        """A custom region without creds/endpoint still yields ``{}``.

        Emitting ``AWS_REGION`` alone would override a real-AWS user's
        ambient region; the block only takes over once a credential or
        endpoint is set.
        """
        assert build_s3_storage_options(S3Settings(region="eu-central-1")) == {}

    def test_full_local_endpoint(self) -> None:
        """Keys + endpoint + http + unsafe-rename map to the AWS_* keys."""
        opts = build_s3_storage_options(
            S3Settings(
                access_key_id="ak",
                secret_access_key="sk",
                endpoint_url="http://127.0.0.1:8333",
                allow_http=True,
                allow_unsafe_rename=True,
            )
        )
        assert opts == {
            "AWS_ACCESS_KEY_ID": "ak",
            "AWS_SECRET_ACCESS_KEY": "sk",
            "AWS_REGION": "us-east-1",
            "AWS_ENDPOINT_URL": "http://127.0.0.1:8333",
            "AWS_ALLOW_HTTP": "true",
            "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
        }

    def test_session_token_activates_and_maps(self) -> None:
        """A session token alone activates the block and maps through."""
        opts = build_s3_storage_options(S3Settings(session_token="tok"))
        assert opts["AWS_SESSION_TOKEN"] == "tok"
        assert opts["AWS_REGION"] == "us-east-1"

    def test_http_flags_omitted_when_false(self) -> None:
        """``allow_http`` / ``allow_unsafe_rename`` only appear when set."""
        opts = build_s3_storage_options(S3Settings(access_key_id="ak"))
        assert "AWS_ALLOW_HTTP" not in opts
        assert "AWS_S3_ALLOW_UNSAFE_RENAME" not in opts


class TestBuildAzureGcs:
    """Azure + GCS option mapping."""

    def test_azure_unconfigured(self) -> None:
        """Empty block → empty dict."""
        assert build_azure_storage_options(AzureSettings()) == {}

    def test_azure_account_key(self) -> None:
        """Account name + key map to the AZURE_* keys."""
        opts = build_azure_storage_options(AzureSettings(account_name="acct", account_key="key"))
        assert opts == {
            "AZURE_STORAGE_ACCOUNT_NAME": "acct",
            "AZURE_STORAGE_ACCOUNT_KEY": "key",
        }

    def test_azure_sas(self) -> None:
        """A SAS token maps through."""
        opts = build_azure_storage_options(AzureSettings(sas_token="sas"))
        assert opts == {"AZURE_STORAGE_SAS_TOKEN": "sas"}

    def test_gcs_unconfigured(self) -> None:
        """Empty block → empty dict."""
        assert build_gcs_storage_options(GCSSettings()) == {}

    def test_gcs_service_account_key(self) -> None:
        """An inline service-account key maps to the GOOGLE_* key."""
        opts = build_gcs_storage_options(GCSSettings(service_account_key="{}"))
        assert opts == {"GOOGLE_SERVICE_ACCOUNT_KEY": "{}"}


class TestResolvers:
    """``NullResolver`` / ``StaticResolver`` / ``storage_options_for``."""

    def test_null_resolver_is_always_empty(self) -> None:
        """The null resolver supplies nothing for any scheme."""
        assert NullResolver().resolve("s3://b/k") == {}
        assert NullResolver().resolve("/tmp/x") == {}

    def test_static_resolver_routes_by_scheme(self) -> None:
        """Each scheme resolves from its own settings block."""
        cfg = ObjectStoreSettings(
            s3=S3Settings(access_key_id="ak"),
            azure=AzureSettings(account_name="acct", account_key="key"),
            gcs=GCSSettings(service_account_key="{}"),
        )
        r = StaticResolver(cfg)
        assert r.resolve("s3://b/k")["AWS_ACCESS_KEY_ID"] == "ak"
        assert r.resolve("s3a://b/k")["AWS_ACCESS_KEY_ID"] == "ak"
        assert r.resolve("abfss://c@a/p")["AZURE_STORAGE_ACCOUNT_NAME"] == "acct"
        assert r.resolve("gs://b/k")["GOOGLE_SERVICE_ACCOUNT_KEY"] == "{}"
        assert r.resolve("/tmp/local") == {}

    def test_static_resolver_reads_live_settings_when_unpinned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no pinned config it reads the (env-driven) process settings."""
        from pointlessql.config import reset_settings_cache

        monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ACCESS_KEY_ID", "env-ak")
        monkeypatch.setenv("POINTLESSQL_OBJECT_STORE_S3_ENDPOINT_URL", "http://h:1")
        reset_settings_cache()
        assert StaticResolver().resolve("s3://b/k")["AWS_ACCESS_KEY_ID"] == "env-ak"

    def test_storage_options_for_collapses_empty_to_none(self) -> None:
        """Local + unconfigured-cloud collapse to ``None`` (byte-stable)."""
        assert storage_options_for("/tmp/x") is None
        assert (
            storage_options_for("s3://b/k", resolver=StaticResolver(ObjectStoreSettings())) is None
        )

    def test_storage_options_for_returns_dict_when_configured(self) -> None:
        """A configured cloud location yields the options dict."""
        cfg = ObjectStoreSettings(s3=S3Settings(access_key_id="ak"))
        opts = storage_options_for("s3://b/k", resolver=StaticResolver(cfg))
        assert opts is not None
        assert opts["AWS_ACCESS_KEY_ID"] == "ak"

    def test_make_resolver_resolves_static(self) -> None:
        """The factory wires a resolver bound to the given settings."""
        cfg = ObjectStoreSettings(s3=S3Settings(access_key_id="ak"))
        resolver = make_resolver(cfg)
        assert resolver.resolve("s3://b/k")["AWS_ACCESS_KEY_ID"] == "ak"
