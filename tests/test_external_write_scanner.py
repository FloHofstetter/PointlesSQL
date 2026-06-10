"""Unit tests for the external (unattributed) Delta-write scanner.

Three seams are exercised: the pure ``_parse_commit_timestamp`` helper,
``scan_table`` against a fake ``deltalake.DeltaTable`` whose history is
diffed against seeded ``agent_run_operations`` rows, and the
``unattributed_writes`` CRUD helpers (list / acknowledge / count).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRunOperation, UnattributedWrite
from pointlessql.services import external_write_scanner as ews
from pointlessql.types import TableFqn

_NOW = _dt.datetime(2026, 6, 1, tzinfo=_dt.UTC)


# --- _parse_commit_timestamp (pure) --------------------------------------


def test_parse_timestamp_epoch_millis() -> None:
    # 2021-01-01T00:00:00Z in epoch millis.
    out = ews._parse_commit_timestamp({"timestamp": 1609459200000})
    assert out == _dt.datetime(2021, 1, 1, tzinfo=_dt.UTC)


def test_parse_timestamp_float_millis() -> None:
    out = ews._parse_commit_timestamp({"timestamp": 1609459200000.0})
    assert out is not None
    assert out.tzinfo is not None


def test_parse_timestamp_iso_string_with_z() -> None:
    out = ews._parse_commit_timestamp({"timestamp": "2026-01-01T00:00:00Z"})
    assert out == _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)


def test_parse_timestamp_missing_is_none() -> None:
    assert ews._parse_commit_timestamp({}) is None


def test_parse_timestamp_bad_string_is_none() -> None:
    assert ews._parse_commit_timestamp({"timestamp": "not-a-date"}) is None


# --- scan_table -----------------------------------------------------------


class _FakeDeltaTable:
    def __init__(self, location: str, *, history: list[dict[str, Any]] | None = None) -> None:
        self.location = location
        self._history = history if history is not None else _FakeDeltaTable._shared

    _shared: list[dict[str, Any]] = []

    def history(self, limit: int = 0) -> list[dict[str, Any]]:
        return list(self._history)


@pytest.fixture
def patch_delta(monkeypatch: pytest.MonkeyPatch):
    import deltalake

    def _install(history: list[dict[str, Any]] | None = None, *, raises: bool = False) -> None:
        def _factory(location: str) -> Any:
            if raises:
                raise RuntimeError("cannot read delta log")
            return _FakeDeltaTable(location, history=history)

        monkeypatch.setattr(deltalake, "DeltaTable", _factory)

    return _install


def _seed_attributed_op(fqn: str, version: int) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRunOperation(
                agent_run_id="run-ews",
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table=fqn,
                delta_version_after=version,
                started_at=_NOW,
            )
        )
        session.commit()


def test_scan_inserts_unattributed_commit(patch_delta: Any) -> None:
    fqn = TableFqn.from_parts("main", "sch", "ews_a")
    patch_delta([{"version": 0, "timestamp": 1609459200000, "operation": "WRITE"}])
    inserted = ews.scan_table(
        app.state.session_factory,
        table_fqn=fqn,
        storage_location="file:///tmp/ews_a",
        now=_NOW,
    )
    assert len(inserted) == 1
    assert inserted[0]["delta_version"] == 0
    assert inserted[0]["operation"] == "WRITE"


def test_scan_skips_attributed_commit(patch_delta: Any) -> None:
    fqn = TableFqn.from_parts("main", "sch", "ews_b")
    _seed_attributed_op(str(fqn), version=5)
    patch_delta([{"version": 5, "timestamp": 1609459200000, "operation": "MERGE"}])
    inserted = ews.scan_table(
        app.state.session_factory,
        table_fqn=fqn,
        storage_location="file:///tmp/ews_b",
        now=_NOW,
    )
    assert inserted == []


def test_scan_is_idempotent(patch_delta: Any) -> None:
    fqn = TableFqn.from_parts("main", "sch", "ews_c")
    history = [{"version": 1, "timestamp": 1609459200000, "operation": "WRITE"}]
    patch_delta(history)
    first = ews.scan_table(app.state.session_factory, table_fqn=fqn, storage_location="x", now=_NOW)
    assert len(first) == 1
    patch_delta(history)
    second = ews.scan_table(
        app.state.session_factory, table_fqn=fqn, storage_location="x", now=_NOW
    )
    assert second == []


def test_scan_history_read_error_returns_empty(patch_delta: Any) -> None:
    fqn = TableFqn.from_parts("main", "sch", "ews_d")
    patch_delta(raises=True)
    assert (
        ews.scan_table(app.state.session_factory, table_fqn=fqn, storage_location="x", now=_NOW)
        == []
    )


def test_scan_skips_non_integer_version(patch_delta: Any) -> None:
    fqn = TableFqn.from_parts("main", "sch", "ews_e")
    patch_delta([{"version": "bad", "timestamp": 1609459200000}])
    assert (
        ews.scan_table(app.state.session_factory, table_fqn=fqn, storage_location="x", now=_NOW)
        == []
    )


# --- CRUD helpers ---------------------------------------------------------


def _add_write(fqn: str, version: int, *, acked: bool = False) -> int:
    factory = app.state.session_factory
    with factory() as session:
        row = UnattributedWrite(
            table_fqn=fqn,
            delta_version=version,
            detected_at=_NOW,
            acknowledged_at=_NOW if acked else None,
            acknowledged_by="admin@x" if acked else None,
        )
        session.add(row)
        session.commit()
        return int(row.id)


def test_list_unattributed_filters_unacknowledged() -> None:
    _add_write("main.crud.t1", 0, acked=False)
    _add_write("main.crud.t1", 1, acked=True)
    rows = ews.list_unattributed(
        app.state.session_factory, only_unacknowledged=True, table_fqn_like="main.crud.t1"
    )
    assert all(r["acknowledged_at"] is None for r in rows)
    assert {r["delta_version"] for r in rows} == {0}


def test_acknowledge_marks_row() -> None:
    write_id = _add_write("main.crud.t2", 0)
    assert ews.acknowledge(app.state.session_factory, write_id, acknowledged_by="bob@x", now=_NOW)
    rows = ews.list_unattributed(app.state.session_factory, table_fqn_like="main.crud.t2")
    assert rows[0]["acknowledged_by"] == "bob@x"


def test_acknowledge_missing_returns_false() -> None:
    assert not ews.acknowledge(app.state.session_factory, 999999, acknowledged_by="bob@x", now=_NOW)


def test_count_unacknowledged_counts_open_rows() -> None:
    before = ews.count_unacknowledged(app.state.session_factory)
    _add_write("main.crud.t3", 0, acked=False)
    after = ews.count_unacknowledged(app.state.session_factory)
    assert after == before + 1
