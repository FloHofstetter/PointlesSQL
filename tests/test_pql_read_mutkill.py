"""Behaviour tests for :func:`pointlessql.pql._read.read_table`.

The high-level ``PQL.table()`` tests in :mod:`tests.test_pql` assert
the return value and the error paths, but never look at the read-audit
row that ``read_table`` is supposed to write into ``query_history``.
That audit insert is the whole reason :func:`read_table` exists as a
choke point, so this file drives it end-to-end against a real
in-memory SQLite session factory and asserts every column the
helper forwards: the synthesised ``SELECT * FROM <fqn>`` text, the
``referenced_tables`` reverse-lookup row, the read-kind discriminator,
the success/failure status, and the timing fields.

No catalog or Delta storage is needed — ``_get_table.sync`` is patched
to return a fixed ``TableInfo`` and the engine is a tiny stub.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import Base, QueryHistory, QueryHistoryTable
from pointlessql.pql import _read
from pointlessql.types import QueryStatus, ReadKind

# A real UUIDv4 string so the 36-char run-id survives
# ``query_history._sanitise_run_id`` and lands in the column.
_RUN_ID = str(uuid.uuid4())


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """An in-memory SQLite session factory with the full schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def wired(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker:  # type: ignore[type-arg]
    """Wire the audit path: bind the factory and the run-id env var.

    ``_record`` only writes when ``POINTLESSQL_AGENT_RUN_ID`` is set
    and ``get_session_factory`` resolves, so both are arranged here.
    """
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", _RUN_ID)
    monkeypatch.setenv("POINTLESSQL_PRINCIPAL", "alice@example.com")
    import pointlessql.db as db

    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    return factory


class _StubEngine:
    """Engine whose ``read`` returns a sentinel and records its arg."""

    def __init__(self, result: Any, *, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.read_arg: str | None = None

    def read(self, storage_location: str) -> Any:
        self.read_arg = storage_location
        if self._raises is not None:
            raise self._raises
        return self._result


def _patch_table(monkeypatch: pytest.MonkeyPatch, storage_location: Any) -> None:
    """Patch ``_get_table.sync`` to return a ``TableInfo``."""
    from soyuz_catalog_client.models.table_info import TableInfo

    fake = MagicMock()
    fake.sync.return_value = TableInfo(storage_location=storage_location, name="tbl")
    monkeypatch.setattr(_read, "_get_table", fake)


def _row(factory: sessionmaker) -> QueryHistory:  # type: ignore[type-arg]
    with factory() as s:
        rows = list(s.scalars(select(QueryHistory)).all())
    assert len(rows) == 1, f"expected exactly one audit row, got {len(rows)}"
    return rows[0]


# ------------------------------------------------------------------
# Happy path — return value AND the success audit row
# ------------------------------------------------------------------


def test_returns_engine_result_and_writes_success_audit_row(
    wired: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful read returns the engine frame and audits a row.

    This pins the success ``_record`` call: the engine's exact return
    value is handed back, the table location is forwarded to the
    engine verbatim, and a single succeeded ``query_history`` row is
    written carrying the FQN, principal, run-id, and read-kind.
    """
    _patch_table(monkeypatch, "/data/cat/sch/tbl")
    sentinel = object()
    engine = _StubEngine(sentinel)

    result = _read.read_table(
        client=MagicMock(),
        engine=engine,  # type: ignore[arg-type]
        full_name="cat.sch.tbl",
        unreachable_msg="nope",
    )

    # Exact engine result is returned unchanged, and the storage
    # location was forwarded to ``engine.read`` verbatim.
    assert result is sentinel
    assert engine.read_arg == "/data/cat/sch/tbl"

    row = _row(wired)
    # ``full_name`` flows into both the synthesised SQL and the
    # referenced-tables reverse-lookup.
    assert row.sql_text == "SELECT * FROM cat.sch.tbl"
    assert row.status == QueryStatus.SUCCEEDED
    assert row.error_message is None
    assert row.read_kind == ReadKind.PQL_TABLE
    assert row.agent_run_id == _RUN_ID
    assert row.user_email == "alice@example.com"
    # Timing fields are real, ordered, and non-negative.
    assert isinstance(row.started_at, datetime.datetime)
    assert isinstance(row.finished_at, datetime.datetime)
    assert row.finished_at >= row.started_at
    assert isinstance(row.duration_ms, int)
    assert row.duration_ms >= 0
    # The reverse-lookup row carries the same FQN.
    with wired() as s:
        refs = list(s.scalars(select(QueryHistoryTable.full_name)).all())
    assert refs == ["cat.sch.tbl"]


def test_audit_fqn_tracks_the_requested_name(
    wired: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audited FQN must be the *requested* name, not a constant.

    Reading a different table writes that table's name into both the
    SQL text and the reverse-lookup, which catches a hard-coded /
    dropped ``full_name`` forward.
    """
    _patch_table(monkeypatch, "/data/x")
    _read.read_table(
        client=MagicMock(),
        engine=_StubEngine("ok"),  # type: ignore[arg-type]
        full_name="other.s.t",
        unreachable_msg="nope",
    )
    row = _row(wired)
    assert row.sql_text == "SELECT * FROM other.s.t"
    with wired() as s:
        refs = list(s.scalars(select(QueryHistoryTable.full_name)).all())
    assert refs == ["other.s.t"]


# ------------------------------------------------------------------
# Failure path — engine.read raises
# ------------------------------------------------------------------


def test_engine_failure_reraises_and_writes_failed_audit_row(
    wired: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the engine raises, the original error propagates unchanged.

    A failed ``query_history`` row is written first, carrying the
    repr of the exception in ``error_message`` and ``status="failed"``.
    This pins the except-branch ``_record`` call and its argument
    forwarding.
    """
    _patch_table(monkeypatch, "/data/boom")
    boom = RuntimeError("engine exploded")
    engine = _StubEngine(None, raises=boom)

    with pytest.raises(RuntimeError, match="engine exploded") as excinfo:
        _read.read_table(
            client=MagicMock(),
            engine=engine,  # type: ignore[arg-type]
            full_name="cat.sch.tbl",
            unreachable_msg="nope",
        )
    # The *same* exception object propagates — not a TypeError from a
    # broken ``_record`` call, and not a swallowed error.
    assert excinfo.value is boom

    row = _row(wired)
    assert row.status == QueryStatus.FAILED
    assert row.sql_text == "SELECT * FROM cat.sch.tbl"
    assert row.error_message == repr(boom)
    assert row.read_kind == ReadKind.PQL_TABLE
    assert isinstance(row.started_at, datetime.datetime)
    assert isinstance(row.finished_at, datetime.datetime)
    assert isinstance(row.duration_ms, int)
    assert row.duration_ms >= 0


# ------------------------------------------------------------------
# storage_location guard — empty string must raise
# ------------------------------------------------------------------


def test_empty_storage_location_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty (falsy) ``storage_location`` is treated as missing.

    ``isinstance(loc, Unset) or not loc`` must short-circuit on the
    empty-string case; an ``and`` there would let the read proceed
    into ``engine.read("")``.  No audit wiring needed — the guard
    fires before the read.
    """
    _patch_table(monkeypatch, "")
    engine = _StubEngine("should-not-be-read")

    with pytest.raises(CatalogNotFoundError, match="no storage_location"):
        _read.read_table(
            client=MagicMock(),
            engine=engine,  # type: ignore[arg-type]
            full_name="cat.sch.tbl",
            unreachable_msg="nope",
        )
    # The guard fired before the engine was touched.
    assert engine.read_arg is None


# ------------------------------------------------------------------
# Audit gating — env-var name + the not-set guard
# ------------------------------------------------------------------


def test_no_audit_row_when_run_id_unset(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no ``POINTLESSQL_AGENT_RUN_ID``, ``_record`` is a no-op.

    The read still succeeds, but no ``query_history`` row is written.
    This pins the env-var name and the ``if not ...: return`` guard:
    flipping either would write a row here (or skip one in the wired
    test above).
    """
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    import pointlessql.db as db

    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    _patch_table(monkeypatch, "/data/x")

    result = _read.read_table(
        client=MagicMock(),
        engine=_StubEngine("frame"),  # type: ignore[arg-type]
        full_name="cat.sch.tbl",
        unreachable_msg="nope",
    )
    assert result == "frame"
    with factory() as s:
        assert list(s.scalars(select(QueryHistory)).all()) == []
