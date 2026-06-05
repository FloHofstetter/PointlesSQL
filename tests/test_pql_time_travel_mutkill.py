"""Mutation-killing tests for :mod:`pointlessql.pql._time_travel`.

These complement ``tests/test_pql_time_travel.py`` by asserting the
*observable side effects* the existing suite ignores:

* the exact arguments forwarded to the generated client lookup
  (``client`` / ``full_name``);
* the exact ``deltalake.DeltaTable`` location and the version /
  timestamp handed to ``load_as_version``;
* every field of the ``query_history`` row built in :func:`_record`
  (status, row_count derived from ``result.shape[0]``, duration,
  error_message, timestamps) on both the success and failure paths;
* the message carried by :class:`CatalogUnavailableError` /
  :class:`CatalogNotFoundError`;
* the truthiness wiring of the ``Unset or not location`` guard,
  which an empty-string location distinguishes from ``and``.

The catalog lookup (``_get_table.sync``) and ``deltalake.DeltaTable``
seams are monkeypatched. ``_record`` is captured so the audit payload
is asserted directly; the function under test never touches a DB.
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
from pointlessql.types import QueryStatus, ReadKind

_UNREACHABLE = "cannot reach catalog"
_LOCATION = "file:///tmp/tt"


class _FakeDeltaTable:
    """Records the constructed location and the requested version."""

    instances: list[_FakeDeltaTable] = []

    def __init__(self, location: Any) -> None:
        self.location = location
        self.loaded: Any = "<unloaded>"
        _FakeDeltaTable.instances.append(self)

    def load_as_version(self, version: Any) -> None:
        self.loaded = version

    def to_pandas(self) -> Any:
        import pandas as pd

        # 4 rows x 2 cols: shape[0]=4 != shape[1]=2, so a shape[0]
        # -> shape[1] mutation is observable in row_count.
        return pd.DataFrame({"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]})


@pytest.fixture
def fake_delta(monkeypatch: pytest.MonkeyPatch) -> type[_FakeDeltaTable]:
    import deltalake

    _FakeDeltaTable.instances = []
    monkeypatch.setattr(deltalake, "DeltaTable", _FakeDeltaTable)
    return _FakeDeltaTable


@pytest.fixture
def fixed_perf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``time.perf_counter`` so ``duration_ms`` is exactly 2500.

    First call (``perf_start``) returns 100.0, the second (when the
    row is built) returns 102.5: ``(102.5 - 100.0) * 1000 == 2500``.
    This makes the duration arithmetic (``* 1000`` vs ``/ 1000`` /
    ``* 1001`` / ``+``) observable as an exact integer.
    """
    seq = iter([100.0, 102.5])

    def _perf() -> float:
        return next(seq)

    monkeypatch.setattr(_time_travel.time, "perf_counter", _perf)


def _patch_get_table(monkeypatch: pytest.MonkeyPatch, result: Any) -> dict[str, Any]:
    """Patch the client lookup; return a dict capturing the call kwargs."""
    captured: dict[str, Any] = {}

    def _sync(*, client: Any, full_name: str) -> Any:
        captured["client"] = client
        captured["full_name"] = full_name
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(_time_travel._get_table, "sync", _sync)
    return captured


def _capture_record(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace ``_record`` with a capturing stub; return the call log."""
    calls: list[dict[str, Any]] = []

    def _rec(**kwargs: Any) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(_time_travel, "_record", _rec)
    return calls


# --- _resolve_storage_location: arguments + guard + messages -------------


def test_resolve_forwards_client_and_full_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_client = object()
    captured = _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    loc = _time_travel._resolve_storage_location(sentinel_client, "cat.sch.tbl", _UNREACHABLE)
    assert loc == _LOCATION
    # Kills client=None / full_name=None forwarding mutations.
    assert captured["client"] is sentinel_client
    assert captured["full_name"] == "cat.sch.tbl"


def test_resolve_empty_string_location_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # location == "" is not Unset but is falsy: `or not location` raises,
    # while the `and` mutant would silently return "".
    _patch_get_table(monkeypatch, TableInfo(storage_location=""))
    with pytest.raises(CatalogNotFoundError):
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)


def test_resolve_unset_location_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_table(monkeypatch, TableInfo())
    with pytest.raises(CatalogNotFoundError):
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)


def test_resolve_connect_error_carries_unreachable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_table(monkeypatch, httpx.ConnectError("down"))
    with pytest.raises(CatalogUnavailableError) as exc_info:
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)
    # Kills CatalogUnavailableError(None).
    assert str(exc_info.value) == _UNREACHABLE


def test_resolve_not_found_message_names_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_table(monkeypatch, None)
    with pytest.raises(CatalogNotFoundError) as exc_info:
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)
    # Kills CatalogNotFoundError(None) for the missing-table branch.
    assert "c.s.t" in str(exc_info.value)


def test_resolve_no_location_message_names_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_table(monkeypatch, TableInfo())
    with pytest.raises(CatalogNotFoundError) as exc_info:
        _time_travel._resolve_storage_location(object(), "c.s.t", _UNREACHABLE)
    assert "c.s.t" in str(exc_info.value)
    assert "storage_location" in str(exc_info.value)


# --- read_table_at_version: delta wiring + audit row ---------------------


def test_read_at_version_wires_location_and_version(
    monkeypatch: pytest.MonkeyPatch,
    fake_delta: type[_FakeDeltaTable],
    fixed_perf: None,
) -> None:
    sentinel_client = object()
    captured = _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    calls = _capture_record(monkeypatch)

    df = _time_travel.read_table_at_version(
        client=sentinel_client,
        full_name="c.s.t",
        version=7,
        unreachable_msg=_UNREACHABLE,
    )

    assert list(df["a"]) == [1, 2, 3, 4]
    # location passed straight through to DeltaTable (kills location=None).
    assert fake_delta.instances[-1].location == _LOCATION
    # exact version reached load_as_version (kills version=None / wrong arg).
    assert fake_delta.instances[-1].loaded == 7
    # resolve received the real client (kills _resolve(None, ...)).
    assert captured["client"] is sentinel_client

    # Exactly one SUCCEEDED audit row with the derived row_count.
    assert len(calls) == 1
    row = calls[0]
    assert row["full_name"] == "c.s.t"
    assert row["status"] is QueryStatus.SUCCEEDED
    assert row["row_count"] == 4  # shape[0], not shape[1] (==2)
    assert row["error_message"] is None
    # (102.5 - 100.0) * 1000 == 2500 — kills the duration arithmetic mutants.
    assert row["duration_ms"] == 2500
    assert isinstance(row["started_at"], datetime.datetime)
    assert isinstance(row["finished_at"], datetime.datetime)
    assert row["started_at"].tzinfo is not None
    assert row["finished_at"].tzinfo is not None


def test_read_at_version_failure_records_failed_row(
    monkeypatch: pytest.MonkeyPatch,
    fake_delta: type[_FakeDeltaTable],
    fixed_perf: None,
) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    calls = _capture_record(monkeypatch)

    def _boom(self: Any, version: Any) -> None:
        raise RuntimeError("no such version")

    monkeypatch.setattr(_FakeDeltaTable, "load_as_version", _boom)

    with pytest.raises(RuntimeError, match="no such version"):
        _time_travel.read_table_at_version(
            client=object(),
            full_name="c.s.t",
            version=99,
            unreachable_msg=_UNREACHABLE,
        )

    assert len(calls) == 1
    row = calls[0]
    assert row["full_name"] == "c.s.t"
    assert row["status"] is QueryStatus.FAILED
    assert row["row_count"] is None
    # error_message embeds the version and the repr of the exception.
    assert row["error_message"] is not None
    assert "version=99" in row["error_message"]
    assert "no such version" in row["error_message"]
    assert isinstance(row["started_at"], datetime.datetime)
    assert isinstance(row["finished_at"], datetime.datetime)
    assert row["started_at"].tzinfo is not None
    assert row["finished_at"].tzinfo is not None
    assert row["duration_ms"] == 2500


def test_read_at_version_connect_error_keeps_message(
    monkeypatch: pytest.MonkeyPatch, fake_delta: type[_FakeDeltaTable]
) -> None:
    # The unreachable_msg must reach _resolve_storage_location intact
    # (kills _resolve_storage_location(..., None) inside the read).
    _patch_get_table(monkeypatch, httpx.ConnectError("down"))
    _capture_record(monkeypatch)
    with pytest.raises(CatalogUnavailableError) as exc_info:
        _time_travel.read_table_at_version(
            client=object(),
            full_name="c.s.t",
            version=1,
            unreachable_msg=_UNREACHABLE,
        )
    assert str(exc_info.value) == _UNREACHABLE


# --- read_table_at_timestamp: validation + delta wiring + audit row ------


def test_read_at_timestamp_naive_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_record(monkeypatch)
    with pytest.raises(ValidationError) as exc_info:
        _time_travel.read_table_at_timestamp(
            client=object(),
            full_name="c.s.t",
            when=datetime.datetime(2026, 1, 1),  # naive
            unreachable_msg=_UNREACHABLE,
        )
    # Exact message: kills ValidationError(None), case-mangled, and
    # XX-wrapped string mutants.
    assert str(exc_info.value) == "table_at_timestamp requires a timezone-aware datetime"
    # Naive input short-circuits before any audit row.
    assert calls == []


def test_read_at_timestamp_accepts_aware_datetime(
    monkeypatch: pytest.MonkeyPatch, fake_delta: type[_FakeDeltaTable]
) -> None:
    # A timezone-aware datetime must NOT raise: kills `is None` -> `is not None`.
    _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    _capture_record(monkeypatch)
    when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    df = _time_travel.read_table_at_timestamp(
        client=object(),
        full_name="c.s.t",
        when=when,
        unreachable_msg=_UNREACHABLE,
    )
    assert list(df["a"]) == [1, 2, 3, 4]


def test_read_at_timestamp_wires_location_and_when(
    monkeypatch: pytest.MonkeyPatch,
    fake_delta: type[_FakeDeltaTable],
    fixed_perf: None,
) -> None:
    sentinel_client = object()
    captured = _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    calls = _capture_record(monkeypatch)
    when = datetime.datetime(2026, 3, 4, 5, 6, 7, tzinfo=datetime.UTC)

    df = _time_travel.read_table_at_timestamp(
        client=sentinel_client,
        full_name="c.s.t",
        when=when,
        unreachable_msg=_UNREACHABLE,
    )

    assert list(df["b"]) == [5, 6, 7, 8]
    assert fake_delta.instances[-1].location == _LOCATION
    # The aware datetime is handed straight to load_as_version.
    assert fake_delta.instances[-1].loaded == when
    assert captured["client"] is sentinel_client

    assert len(calls) == 1
    row = calls[0]
    assert row["full_name"] == "c.s.t"
    assert row["status"] is QueryStatus.SUCCEEDED
    assert row["row_count"] == 4
    assert row["error_message"] is None
    assert row["duration_ms"] == 2500
    assert row["started_at"].tzinfo is not None
    assert row["finished_at"].tzinfo is not None


def test_read_at_timestamp_failure_records_failed_row(
    monkeypatch: pytest.MonkeyPatch,
    fake_delta: type[_FakeDeltaTable],
    fixed_perf: None,
) -> None:
    _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    calls = _capture_record(monkeypatch)
    when = datetime.datetime(2026, 3, 4, 5, 6, 7, tzinfo=datetime.UTC)

    def _boom(self: Any, version: Any) -> None:
        raise RuntimeError("kaboom-ts")

    monkeypatch.setattr(_FakeDeltaTable, "load_as_version", _boom)

    with pytest.raises(RuntimeError, match="kaboom-ts"):
        _time_travel.read_table_at_timestamp(
            client=object(),
            full_name="c.s.t",
            when=when,
            unreachable_msg=_UNREACHABLE,
        )

    assert len(calls) == 1
    row = calls[0]
    assert row["status"] is QueryStatus.FAILED
    assert row["row_count"] is None
    assert row["error_message"] is not None
    # error_message embeds the ISO timestamp and the exception repr.
    assert when.isoformat() in row["error_message"]
    assert "kaboom-ts" in row["error_message"]
    assert row["duration_ms"] == 2500
    assert row["started_at"].tzinfo is not None
    assert row["finished_at"].tzinfo is not None


def test_read_at_timestamp_connect_error_keeps_message(
    monkeypatch: pytest.MonkeyPatch, fake_delta: type[_FakeDeltaTable]
) -> None:
    _patch_get_table(monkeypatch, httpx.ConnectError("down"))
    _capture_record(monkeypatch)
    when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    with pytest.raises(CatalogUnavailableError) as exc_info:
        _time_travel.read_table_at_timestamp(
            client=object(),
            full_name="c.s.t",
            when=when,
            unreachable_msg=_UNREACHABLE,
        )
    assert str(exc_info.value) == _UNREACHABLE


# --- _record: env gate + forwarded payload -------------------------------


def _patch_record_read(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture calls to ``record_read`` (positional factory + kwargs)."""
    calls: list[dict[str, Any]] = []

    def _rr(factory: Any, /, **kwargs: Any) -> int | None:
        calls.append({"factory": factory, **kwargs})
        return None

    monkeypatch.setattr(_time_travel, "record_read", _rr)
    return calls


def _make_record_kwargs() -> dict[str, Any]:
    start = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    end = datetime.datetime(2026, 1, 1, 0, 0, 1, tzinfo=datetime.UTC)
    return {
        "full_name": "c.s.t",
        "started_at": start,
        "finished_at": end,
        # FAILED (not the SUCCEEDED default) so a dropped status= kwarg
        # — which would fall back to the default — is observable.
        "status": QueryStatus.FAILED,
        "row_count": 42,
        "duration_ms": 17,
        "error_message": "boom",
    }


def test_record_skips_when_no_agent_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    calls = _patch_record_read(monkeypatch)
    _time_travel._record(**_make_record_kwargs())
    # Kills `if not ... :` -> `if ...:` (would invert and call record_read).
    assert calls == []


def test_record_forwards_full_payload_when_gated_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "run-123")
    calls = _patch_record_read(monkeypatch)

    kwargs = _make_record_kwargs()
    _time_travel._record(**kwargs)

    assert len(calls) == 1
    rr = calls[0]
    # With no DB initialised, get_session_factory() raises and the
    # except branch leaves factory at None (kills factory="" mutant).
    assert rr["factory"] is None
    # read_kind + payload must be forwarded verbatim.
    assert rr["read_kind"] is ReadKind.PQL_TABLE_AT_VERSION
    assert rr["table_fqn"] == "c.s.t"
    assert rr["started_at"] == kwargs["started_at"]
    assert rr["finished_at"] == kwargs["finished_at"]
    assert rr["status"] is QueryStatus.FAILED
    assert rr["row_count"] == 42
    assert rr["duration_ms"] == 17
    assert rr["error_message"] == "boom"


def test_record_uses_exact_env_var_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A lookalike / lowercased env var must NOT trigger the audit write.
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    monkeypatch.setenv("pointlessql_agent_run_id", "run-xyz")
    calls = _patch_record_read(monkeypatch)
    _time_travel._record(**_make_record_kwargs())
    assert calls == []


def test_record_forwards_the_real_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # When the DB IS initialised, get_session_factory() returns a live
    # factory and that exact object must be forwarded to record_read.
    # Pins `factory = get_session_factory()` (not `factory = None`) and
    # `record_read(factory, ...)` (not `record_read(None, ...)`): with a
    # successful lookup the except branch never runs, so a None on either
    # line is only visible when the factory is a non-None sentinel.
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "run-123")
    sentinel_factory = object()

    import pointlessql.db as db

    monkeypatch.setattr(db, "get_session_factory", lambda: sentinel_factory)
    calls = _patch_record_read(monkeypatch)

    _time_travel._record(**_make_record_kwargs())

    assert len(calls) == 1
    assert calls[0]["factory"] is sentinel_factory


# --- read_table_at_timestamp failure path: full_name forwarding ----------


def test_read_at_timestamp_failure_row_keeps_full_name(
    monkeypatch: pytest.MonkeyPatch,
    fake_delta: type[_FakeDeltaTable],
    fixed_perf: None,
) -> None:
    # On the failure path the audit row must still carry the real
    # full_name. Kills both full_name=None and a dropped full_name=
    # kwarg in the except-branch _record call (the latter leaves the
    # key absent, so the lookup raises KeyError on the mutant).
    _patch_get_table(monkeypatch, TableInfo(storage_location=_LOCATION))
    calls = _capture_record(monkeypatch)
    when = datetime.datetime(2026, 3, 4, 5, 6, 7, tzinfo=datetime.UTC)

    def _boom(self: Any, version: Any) -> None:
        raise RuntimeError("kaboom-ts")

    monkeypatch.setattr(_FakeDeltaTable, "load_as_version", _boom)

    with pytest.raises(RuntimeError, match="kaboom-ts"):
        _time_travel.read_table_at_timestamp(
            client=object(),
            full_name="c.s.t",
            when=when,
            unreachable_msg=_UNREACHABLE,
        )

    assert len(calls) == 1
    assert calls[0]["full_name"] == "c.s.t"
