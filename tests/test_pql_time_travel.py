"""Unit tests for the PQL time-travel read helpers.

The helpers resolve a UC name to a storage location through the generated
client, then hand off to ``deltalake``. Both seams are monkeypatched: the
catalog lookup (``_get_table.sync``) and ``deltalake.DeltaTable``. The
``query_history`` audit row only fires when ``POINTLESSQL_AGENT_RUN_ID`` is
set, so with it unset (the default here) the read path touches no DB.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pytest
from soyuz_catalog_client.models.table_info import TableInfo

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql import _time_travel

_UNREACHABLE = "cannot reach catalog"


class _FakeDeltaTable:
    """Stand-in for ``deltalake.DeltaTable`` recording the requested version."""

    def __init__(self, location: str, storage_options: Any = None) -> None:
        self.location = location
        self.storage_options = storage_options
        self.loaded: Any = None

    def load_as_version(self, version: Any) -> None:
        self.loaded = version

    def to_pandas(self) -> Any:
        import pandas as pd

        return pd.DataFrame({"a": [1, 2, 3]})


@pytest.fixture
def fake_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    import deltalake

    monkeypatch.setattr(deltalake, "DeltaTable", _FakeDeltaTable)


def _patch_get_table(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    """Monkeypatch the generated client lookup to return/raise *result*."""

    def _sync(*, client: Any, full_name: str) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(_time_travel._get_table, "sync", _sync)


# --- _resolve_storage_location -------------------------------------------


def test_resolve_returns_storage_location(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location="file:///tmp/t"))
    loc = _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)
    assert loc == "file:///tmp/t"


def test_resolve_rejects_two_part_name() -> None:
    with pytest.raises(ValidationError):
        _time_travel._resolve_storage_location(object(), "c.s", _UNREACHABLE)


def test_resolve_missing_table_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_table(monkeypatch, None)
    with pytest.raises(CatalogNotFoundError):
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)


def test_resolve_table_without_location_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_table(monkeypatch, TableInfo())
    with pytest.raises(CatalogNotFoundError):
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)


def test_resolve_connect_error_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_table(monkeypatch, httpx.ConnectError("down"))
    with pytest.raises(CatalogUnavailableError):
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)


# --- read_table_at_version -----------------------------------------------


def test_read_at_version_returns_frame(monkeypatch: pytest.MonkeyPatch, fake_delta: None) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location="file:///tmp/t"))
    df = _time_travel.read_table_at_version(
        client=object(), full_name="c.s.t", version=2, unreachable_msg=_UNREACHABLE
    )
    assert list(df["a"]) == [1, 2, 3]


def test_read_at_version_propagates_delta_error(
    monkeypatch: pytest.MonkeyPatch, fake_delta: None
) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location="file:///tmp/t"))

    def _boom(self: Any, version: Any) -> None:
        raise RuntimeError("no such version")

    monkeypatch.setattr(_FakeDeltaTable, "load_as_version", _boom)
    with pytest.raises(RuntimeError, match="no such version"):
        _time_travel.read_table_at_version(
            client=object(), full_name="c.s.t", version=99, unreachable_msg=_UNREACHABLE
        )


# --- read_table_at_timestamp ---------------------------------------------


def test_read_at_timestamp_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _time_travel.read_table_at_timestamp(
            client=object(),
            full_name="c.s.t",
            when=datetime.datetime(2026, 1, 1),  # naive
            unreachable_msg=_UNREACHABLE,
        )


def test_read_at_timestamp_returns_frame(monkeypatch: pytest.MonkeyPatch, fake_delta: None) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location="file:///tmp/t"))
    when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    df = _time_travel.read_table_at_timestamp(
        client=object(), full_name="c.s.t", when=when, unreachable_msg=_UNREACHABLE
    )
    assert list(df["a"]) == [1, 2, 3]
