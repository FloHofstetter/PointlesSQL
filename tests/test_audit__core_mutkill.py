"""Behaviour tests targeting surviving mutants in
:mod:`pointlessql.services.audit._core`.

These tests pin the retention-cutoff comparison in
:func:`pointlessql.services.audit._core.cleanup_old_entries`: a row
whose ``created_at`` equals the cutoff instant exactly is *kept*
(``created_at < cutoff`` is strict), while every strictly-older row
is pruned.

The cutoff is normally ``now() - retention_days`` evaluated inside the
function, which makes the exact-boundary case impossible to seed from
the outside. The tests below pin ``now()`` to a fixed instant by
swapping the module-level ``datetime`` reference in ``_core`` for a
namespace whose ``datetime.now`` returns that instant, so the cutoff
is deterministic and a row can be placed exactly on it.

The fixtures reuse the in-memory SQLite engine + seeded workspace
wired by ``tests/conftest.py`` through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import logging
import types
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AuditLog
from pointlessql.services.audit import _core


def _factory() -> Any:
    return app.state.session_factory


def _seed_audit_row(created_at: datetime.datetime, action: str) -> None:
    with _factory()() as s:
        s.add(
            AuditLog(
                workspace_id=1,
                user_id=1,
                user_email="a@x.com",
                actor_role="user",
                action=action,
                target="t",
                client_ip=None,
                detail=None,
                created_at=created_at,
            )
        )
        s.commit()


class _FixedDateTime(datetime.datetime):
    """``datetime`` subclass whose ``now`` returns a frozen instant."""

    _fixed: datetime.datetime = datetime.datetime(2024, 6, 10, 12, 0, 0, tzinfo=datetime.UTC)

    @classmethod
    def now(cls, tz: Any = None) -> datetime.datetime:  # type: ignore[override]
        return cls._fixed


def _freeze_core_now(monkeypatch: pytest.MonkeyPatch, instant: datetime.datetime) -> None:
    """Pin ``_core``'s view of the wall clock to ``instant``.

    Keeps ``UTC`` and ``timedelta`` intact so the cutoff arithmetic in
    :func:`cleanup_old_entries` still works; only ``datetime.now`` is
    frozen.
    """
    _FixedDateTime._fixed = instant
    fake = types.SimpleNamespace(
        datetime=_FixedDateTime,
        UTC=datetime.UTC,
        timedelta=datetime.timedelta,
    )
    monkeypatch.setattr(_core, "datetime", fake)


def test_cleanup_keeps_row_exactly_at_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # The cutoff comparison is strict (``created_at < cutoff``): a row
    # whose timestamp equals the cutoff is retained. A ``<=`` mutant
    # would prune it too, deleting 2 rows instead of 1.
    fixed_now = datetime.datetime(2024, 6, 10, 12, 0, 0, tzinfo=datetime.UTC)
    _freeze_core_now(monkeypatch, fixed_now)
    retention_days = 7
    cutoff = fixed_now - datetime.timedelta(days=retention_days)

    _seed_audit_row(cutoff, "at_cutoff")
    _seed_audit_row(cutoff - datetime.timedelta(seconds=1), "older")

    deleted = _core.cleanup_old_entries(_factory(), retention_days=retention_days)

    assert deleted == 1
    with _factory()() as s:
        remaining = {r.action for r in s.scalars(select(AuditLog))}
    assert remaining == {"at_cutoff"}


def test_cleanup_prunes_row_just_past_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # Companion to the boundary case: a row one microsecond older than
    # the cutoff is strictly less than it and must be pruned, confirming
    # the comparison fires on the deleting side of the boundary.
    fixed_now = datetime.datetime(2024, 6, 10, 12, 0, 0, tzinfo=datetime.UTC)
    _freeze_core_now(monkeypatch, fixed_now)
    retention_days = 7
    cutoff = fixed_now - datetime.timedelta(days=retention_days)

    _seed_audit_row(cutoff - datetime.timedelta(microseconds=1), "just_past")

    deleted = _core.cleanup_old_entries(_factory(), retention_days=retention_days)

    assert deleted == 1
    with _factory()() as s:
        assert s.scalar(select(AuditLog)) is None


# ---------------------------------------------------------------------
# cleanup_old_entries — log emissions on the prune + failure paths
# ---------------------------------------------------------------------


class _BoomFactory:
    """Session factory that raises the moment it is opened.

    Drives ``cleanup_old_entries`` into its ``except`` branch so the
    warning-log emission (message, args, and ``exc_info``) is
    observable without touching the DB.
    """

    def __call__(self) -> Any:  # noqa: D102 — see class docstring
        raise RuntimeError("kaboom")


def _warning_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """Return the single WARNING record emitted by ``_core``."""
    warnings = [
        r for r in caplog.records if r.name == _core.__name__ and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    return warnings[0]


def test_cleanup_prune_emits_info_with_count_and_retention(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The success path logs an INFO line when at least one row is
    # pruned.  Blanking the format string (the ``XX...XX`` mutant)
    # changes the rendered message; the count/retention args make it
    # human-readable, so assert both the literal text and the
    # substituted values.
    now = datetime.datetime.now(datetime.UTC)
    _seed_audit_row(now - datetime.timedelta(days=10), "old")

    with caplog.at_level(logging.INFO, logger=_core.__name__):
        deleted = _core.cleanup_old_entries(_factory(), retention_days=3)

    assert deleted == 1
    infos = [r for r in caplog.records if r.name == _core.__name__ and r.levelno == logging.INFO]
    assert len(infos) == 1
    rendered = infos[0].getMessage()
    assert rendered == "audit: pruned 1 row(s) older than 3 day(s)"


def test_cleanup_failure_logs_warning_message_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The failure path swallows the error and logs a WARNING.  The
    # blanked-format-string mutant turns the message into ``XX...XX``;
    # pin the exact rendered text (which also embeds the retention arg).
    with caplog.at_level(logging.WARNING, logger=_core.__name__):
        deleted = _core.cleanup_old_entries(_BoomFactory(), retention_days=7)

    assert deleted == 0
    rec = _warning_record(caplog)
    assert rec.getMessage() == "audit: cleanup_old_entries failed after 0 row(s) (retention=7)"


def test_cleanup_failure_warning_keeps_format_string_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Dropping the format-string positional promotes ``retention_days``
    # to the message itself, rendering ``"7"``.  Assert the message
    # still carries the descriptive prefix.
    with caplog.at_level(logging.WARNING, logger=_core.__name__):
        _core.cleanup_old_entries(_BoomFactory(), retention_days=7)

    rec = _warning_record(caplog)
    assert rec.getMessage().startswith("audit: cleanup_old_entries failed")


def test_cleanup_failure_warning_substitutes_retention_arg(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Dropping the ``retention_days`` positional leaves the ``%d``
    # placeholder unsubstituted.  Assert it was filled in with the
    # actual retention value and no raw ``%d`` survives.
    with caplog.at_level(logging.WARNING, logger=_core.__name__):
        _core.cleanup_old_entries(_BoomFactory(), retention_days=13)

    rec = _warning_record(caplog)
    rendered = rec.getMessage()
    assert "retention=13" in rendered
    assert "%d" not in rendered


def test_cleanup_failure_warning_attaches_exception_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # ``exc_info=True`` attaches the live ``(type, value, tb)`` triple to
    # the record.  The ``exc_info=None`` / ``exc_info=False`` / dropped
    # mutants all strip that triple, so assert a real 3-tuple naming the
    # raised exception type is present.
    with caplog.at_level(logging.WARNING, logger=_core.__name__):
        _core.cleanup_old_entries(_BoomFactory(), retention_days=7)

    rec = _warning_record(caplog)
    assert isinstance(rec.exc_info, tuple)
    assert len(rec.exc_info) == 3
    assert rec.exc_info[0] is RuntimeError
    assert isinstance(rec.exc_info[1], RuntimeError)


def test_cleanup_prunes_large_backlog_across_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    # With the batch size below the backlog, the sweep must loop over
    # several commits and still remove every stale row while keeping the
    # fresh ones — a non-looping mutant would prune only the first batch.
    fixed_now = datetime.datetime(2024, 6, 10, 12, 0, 0, tzinfo=datetime.UTC)
    _freeze_core_now(monkeypatch, fixed_now)
    monkeypatch.setattr(_core, "_AUDIT_PRUNE_BATCH", 2)
    old = fixed_now - datetime.timedelta(days=30)
    fresh = fixed_now - datetime.timedelta(days=1)
    for i in range(5):
        _seed_audit_row(old, f"old-{i}")
    for i in range(2):
        _seed_audit_row(fresh, f"fresh-{i}")

    deleted = _core.cleanup_old_entries(_factory(), retention_days=7)

    assert deleted == 5
    with _factory()() as s:
        remaining = {r.action for r in s.scalars(select(AuditLog))}
    assert remaining == {"fresh-0", "fresh-1"}
