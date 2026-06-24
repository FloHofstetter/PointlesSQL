"""Mutation-kill tests for ``pointlessql.pql._read._record`` forwarding.

The audit-row write forwards its measured fields to ``record_read``; pin the
row_count value and the read_kind label so a dropped/None'd kwarg is caught.
"""

from __future__ import annotations

import datetime
from typing import Any

from pointlessql.pql import _read
from pointlessql.types import QueryStatus, ReadKind


def test_record_forwards_row_count_and_read_kind(monkeypatch: Any) -> None:
    """``_record`` forwards row_count verbatim and labels the read PQL_TABLE."""
    # kills row_count=row_count -> None, the dropped row_count= kwarg,
    # and the dropped read_kind=ReadKind.PQL_TABLE kwarg
    captured: dict[str, Any] = {}

    def fake_record_read(factory: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        captured["factory"] = factory

    monkeypatch.setattr(_read, "record_read", fake_record_read)
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: "FACTORY")
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "run-1")

    now = datetime.datetime.now(datetime.UTC)
    _read._record(
        full_name="c.s.t",
        started_at=now,
        finished_at=now,
        status=QueryStatus.SUCCEEDED,
        row_count=42,
        duration_ms=10,
        error_message=None,
    )
    assert captured["row_count"] == 42
    assert captured["read_kind"] == ReadKind.PQL_TABLE
