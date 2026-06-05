"""Behaviour tests targeting a surviving mutant in ``pointlessql.services.audit._read``.

The Delta-direct read instrumentation swallows any failure from the
``query_history`` insert (a broken audit must never break the read) and
records the failure via :meth:`logging.Logger.exception`.  This module
pins the exact log message that gets emitted on that error path so a
silently-mangled message string is caught.
"""

from __future__ import annotations

import datetime
import logging

import pytest

from pointlessql.services.audit import _read


def test_record_read_logs_exact_message_when_insert_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Force the audit insert to fail; the read must not raise, but the
    # failure is recorded via ``logger.exception`` with a fixed message.
    def boom(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(_read, "record_query", boom)

    started = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    finished = datetime.datetime(2024, 1, 2, tzinfo=datetime.UTC)

    with caplog.at_level(logging.ERROR, logger=_read.logger.name):
        out = _read.record_read(
            object(),  # truthy factory so we hit the insert path
            table_fqn="cat.sch.tbl",
            started_at=started,
            finished_at=finished,
        )

    # Error path returns ``None`` (read is unaffected by audit failure).
    assert out is None

    records = [r for r in caplog.records if r.name == _read.logger.name]
    assert records, "expected an audit-failure log record"
    record = records[-1]
    # The message string must be the exact, un-mangled literal — a
    # mutated message ("XXread_audit: failed to recordXX") would fail.
    assert record.getMessage() == "read_audit: failed to record"
    # The error path uses ``logger.exception`` → ERROR level with exc info.
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
