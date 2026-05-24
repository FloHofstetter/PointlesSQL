"""Tests for the get_settings() LRU cache facade introduced ."""

from __future__ import annotations

import os

import pytest

from pointlessql.config import Settings, get_settings, reset_settings_cache


def test_get_settings_returns_singleton() -> None:
    """Two get_settings() calls return the same object instance."""
    a = get_settings()
    b = get_settings()
    assert a is b


def test_get_settings_returns_settings_subtype() -> None:
    """The cached object is a real Settings instance."""
    s = get_settings()
    assert isinstance(s, Settings)


def test_reset_settings_cache_invalidates() -> None:
    """After reset, the next get_settings() returns a fresh instance."""
    a = get_settings()
    reset_settings_cache()
    b = get_settings()
    assert a is not b


def test_reset_picks_up_env_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    """An env-var mutation takes effect after reset_settings_cache().

    Without the reset, the cached Settings keeps the env value it
    saw at first construction.  This test makes the cache contract
    explicit: env mutations require a reset.
    """
    monkeypatch.setenv("POINTLESSQL_SOYUZ_CATALOG_URL", "http://example.test:9999")
    reset_settings_cache()
    s = get_settings()
    assert s.soyuz.catalog_url == "http://example.test:9999"

    # Now mutate without reset — cache still holds the prior value.
    monkeypatch.setenv("POINTLESSQL_SOYUZ_CATALOG_URL", "http://changed.test:1234")
    assert get_settings().soyuz.catalog_url == "http://example.test:9999"

    # After reset the new env value wins.
    reset_settings_cache()
    assert get_settings().soyuz.catalog_url == "http://changed.test:1234"


def test_get_settings_does_not_leak_env_between_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache reset clears state — no carry-over across env scopes."""
    monkeypatch.setenv("POINTLESSQL_SOYUZ_CATALOG_URL", "http://scope1.test")
    reset_settings_cache()
    s1 = get_settings()
    monkeypatch.delenv("POINTLESSQL_SOYUZ_CATALOG_URL", raising=False)
    reset_settings_cache()
    s2 = get_settings()
    # Both observable as different instances driven by different env states.
    assert s1 is not s2
    assert s1.soyuz.catalog_url == "http://scope1.test"
    # Without the env var, the default takes over (not the previous URL).
    assert s2.soyuz.catalog_url != "http://scope1.test"


def test_autouse_fixture_clears_between_tests_part_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First half of a paired test: set env, fetch, check value.

    Companion test ``part_two`` asserts the env is gone in the next
    test — proving the conftest autouse fixture clears the cache.
    """
    monkeypatch.setenv("POINTLESSQL_SOYUZ_CATALOG_URL", "http://pairtest.local:7777")
    reset_settings_cache()
    assert get_settings().soyuz.catalog_url == "http://pairtest.local:7777"


def test_autouse_fixture_clears_between_tests_part_two() -> None:
    """Companion to part_one — env from prior test must not leak through cache."""
    # monkeypatch is function-scoped so the env is already cleaned up;
    # the cache reset is what guarantees the next get_settings() re-reads.
    assert os.environ.get("POINTLESSQL_SOYUZ_CATALOG_URL") != "http://pairtest.local:7777"
    assert get_settings().soyuz.catalog_url != "http://pairtest.local:7777"
