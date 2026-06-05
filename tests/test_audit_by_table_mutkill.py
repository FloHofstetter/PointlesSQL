"""Behaviour tests targeting surviving mutants in ``by_table``.

These tests pin observable outputs of the reverse-index
``runs by table`` service
(:mod:`pointlessql.services.audit.by_table`): the ``since``/``until``
boundary semantics on each kind axis (touched/written/read), the
newest-first ordering, the ``limit`` cap, and the verbatim
forwarding of ``since``/``until``/``limit`` from the public
``runs_by_table`` dispatcher into each helper.

The fixtures reuse the in-memory SQLite engine + per-test re-seeded
workspace wired by ``tests/conftest.py`` through
``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import uuid

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageValueChange,
    QueryHistory,
    QueryHistoryTable,
)
from pointlessql.services.audit import by_table


def _factory() -> object:
    return app.state.session_factory


# ---------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------


def _seed_run(
    *,
    run_id: str,
    started_at: datetime.datetime,
    tables_touched: str | None = None,
    principal: str = "alice@example.com",
) -> None:
    with _factory()() as s:  # type: ignore[operator]
        s.add(
            AgentRun(
                id=run_id,
                principal=principal,
                agent_id="etl",
                notebook_path="nb.py",
                status="succeeded",
                tables_touched=tables_touched,
                started_at=started_at,
                finished_at=started_at,
            )
        )
        s.commit()


def _seed_written_run(*, run_id: str, started_at: datetime.datetime, fqn: str) -> None:
    """Seed a run that wrote ``fqn`` via an op row (the written axis)."""
    _seed_run(run_id=run_id, started_at=started_at)
    with _factory()() as s:  # type: ignore[operator]
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table=fqn,
                rows_affected=1,
                started_at=started_at,
                finished_at=started_at,
            )
        )
        s.commit()


def _seed_read_run(*, run_id: str, started_at: datetime.datetime, fqn: str) -> None:
    """Seed a run that read ``fqn`` via query_history (the read axis)."""
    _seed_run(run_id=run_id, started_at=started_at)
    with _factory()() as s:  # type: ignore[operator]
        qh = QueryHistory(
            user_id=1,
            user_email="alice@example.com",
            sql_text=f"SELECT * FROM {fqn}",
            started_at=started_at,
            finished_at=started_at,
            status="succeeded",
            agent_run_id=run_id,
            read_kind="pql_table",
        )
        s.add(qh)
        s.flush()
        s.add(
            QueryHistoryTable(
                query_history_id=qh.id,
                full_name=fqn,
                access_type="read",
            )
        )
        s.commit()


# Three timestamps spanning a window: a row before the since-bound, a
# row exactly on the since-bound (inclusive → kept), and a row exactly
# on the until-bound (exclusive → dropped).
_BASE = datetime.datetime(2024, 6, 1, 12, 0, tzinfo=datetime.UTC)
_BEFORE = _BASE - datetime.timedelta(hours=1)
_AT_SINCE = _BASE
_AT_UNTIL = _BASE + datetime.timedelta(hours=2)


# ---------------------------------------------------------------------
# _by_read — since/until boundary, limit, ordering
# ---------------------------------------------------------------------


def test_by_read_since_inclusive_until_exclusive() -> None:
    fqn = "cat.sch.readbound"
    before = str(uuid.uuid4())
    at_since = str(uuid.uuid4())
    at_until = str(uuid.uuid4())
    _seed_read_run(run_id=before, started_at=_BEFORE, fqn=fqn)
    _seed_read_run(run_id=at_since, started_at=_AT_SINCE, fqn=fqn)
    _seed_read_run(run_id=at_until, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(
        _factory(),
        fqn=fqn,
        kind="read",
        since=_AT_SINCE,
        until=_AT_UNTIL,
    )
    got = {r["id"] for r in rows}
    # since uses ``>=`` (inclusive) so at_since is IN; a ``>`` mutant or
    # a ``where(None)`` / ``stmt = None`` mutant drops/keeps it wrongly.
    # until uses ``<`` (exclusive) so at_until is OUT; a ``<=`` mutant
    # would let it in. before is always out.
    assert got == {at_since}


def test_by_read_since_only_filters_strictly_older() -> None:
    fqn = "cat.sch.readsince"
    older = str(uuid.uuid4())
    at_since = str(uuid.uuid4())
    _seed_read_run(run_id=older, started_at=_BEFORE, fqn=fqn)
    _seed_read_run(run_id=at_since, started_at=_AT_SINCE, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", since=_AT_SINCE)
    got = {r["id"] for r in rows}
    # A ``stmt = None`` mutant for the since branch crashes (None has no
    # ``.where``); a ``where(None)`` mutant drops the filter and lets the
    # older row through. Original keeps only the at-or-after row.
    assert got == {at_since}


def test_by_read_until_only_drops_at_or_after_bound() -> None:
    fqn = "cat.sch.readuntil"
    inside = str(uuid.uuid4())
    on_bound = str(uuid.uuid4())
    _seed_read_run(run_id=inside, started_at=_AT_SINCE, fqn=fqn)
    _seed_read_run(run_id=on_bound, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", until=_AT_UNTIL)
    got = {r["id"] for r in rows}
    # ``< until`` excludes the on-bound row; a ``<=`` mutant includes it,
    # and a ``where(None)``/``stmt = None`` mutant disables the filter.
    assert got == {inside}


def test_by_read_limit_caps_returned_rows() -> None:
    fqn = "cat.sch.readlimit"
    for i in range(3):
        _seed_read_run(
            run_id=str(uuid.uuid4()),
            started_at=_BASE + datetime.timedelta(minutes=i),
            fqn=fqn,
        )
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", limit=2)
    # ``.limit(limit)`` caps at 2; a ``.limit(None)`` mutant returns all 3.
    assert len(rows) == 2


def test_by_read_orders_newest_first() -> None:
    fqn = "cat.sch.readorder"
    # Insert in ASCENDING started_at order so rowid order is the reverse
    # of the DESC order the query must impose.
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, rid in enumerate(ids):
        _seed_read_run(run_id=rid, started_at=_BASE + datetime.timedelta(hours=i), fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read")
    # ``order_by(started_at.desc())`` → newest (last inserted) first.
    # An ``order_by(None)`` mutant falls back to insertion order and
    # returns the oldest row first.
    assert [r["id"] for r in rows] == list(reversed(ids))


# ---------------------------------------------------------------------
# _by_touched — ordering
# ---------------------------------------------------------------------


def test_by_touched_orders_newest_first() -> None:
    touched = '["cat.sch.touchorder"]'
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, rid in enumerate(ids):
        _seed_run(
            run_id=rid,
            started_at=_BASE + datetime.timedelta(hours=i),
            tables_touched=touched,
        )
    rows = by_table.runs_by_table(_factory(), fqn="cat.sch.touchorder", kind="touched")
    # DESC ordering returns newest first; ``order_by(None)`` returns the
    # rows in insertion (oldest-first) order.
    assert [r["id"] for r in rows] == list(reversed(ids))


# ---------------------------------------------------------------------
# _by_written — since/until boundary, limit, ordering
# ---------------------------------------------------------------------


def test_by_written_since_inclusive_until_exclusive() -> None:
    fqn = "cat.sch.writebound"
    before = str(uuid.uuid4())
    at_since = str(uuid.uuid4())
    at_until = str(uuid.uuid4())
    _seed_written_run(run_id=before, started_at=_BEFORE, fqn=fqn)
    _seed_written_run(run_id=at_since, started_at=_AT_SINCE, fqn=fqn)
    _seed_written_run(run_id=at_until, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(
        _factory(),
        fqn=fqn,
        kind="written",
        since=_AT_SINCE,
        until=_AT_UNTIL,
    )
    got = {r["id"] for r in rows}
    # since ``>=`` inclusive (at_since IN, ``>`` mutant drops it);
    # until ``<`` exclusive (at_until OUT, ``<=`` mutant adds it).
    assert got == {at_since}


def test_by_written_since_only_filters_strictly_older() -> None:
    fqn = "cat.sch.writesince"
    older = str(uuid.uuid4())
    at_since = str(uuid.uuid4())
    _seed_written_run(run_id=older, started_at=_BEFORE, fqn=fqn)
    _seed_written_run(run_id=at_since, started_at=_AT_SINCE, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", since=_AT_SINCE)
    got = {r["id"] for r in rows}
    # ``stmt = None`` crashes; ``where(None)`` disables the filter and
    # lets the older row through. Original keeps only at-or-after.
    assert got == {at_since}


def test_by_written_until_only_drops_at_or_after_bound() -> None:
    fqn = "cat.sch.writeuntil"
    inside = str(uuid.uuid4())
    on_bound = str(uuid.uuid4())
    _seed_written_run(run_id=inside, started_at=_AT_SINCE, fqn=fqn)
    _seed_written_run(run_id=on_bound, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", until=_AT_UNTIL)
    got = {r["id"] for r in rows}
    # ``< until`` drops the on-bound row; ``<=`` keeps it; a disabled
    # filter keeps it too.
    assert got == {inside}


def test_by_written_limit_caps_returned_rows() -> None:
    fqn = "cat.sch.writelimit"
    for i in range(3):
        _seed_written_run(
            run_id=str(uuid.uuid4()),
            started_at=_BASE + datetime.timedelta(minutes=i),
            fqn=fqn,
        )
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", limit=2)
    # ``.limit(2)`` caps; ``.limit(None)`` returns all 3.
    assert len(rows) == 2


def test_by_written_orders_newest_first() -> None:
    fqn = "cat.sch.writeorder"
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, rid in enumerate(ids):
        _seed_written_run(run_id=rid, started_at=_BASE + datetime.timedelta(hours=i), fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written")
    # DESC ordering newest-first; ``order_by(None)`` → insertion order.
    assert [r["id"] for r in rows] == list(reversed(ids))


# ---------------------------------------------------------------------
# runs_by_table dispatcher — verbatim since/until/limit forwarding
# ---------------------------------------------------------------------


def test_runs_by_table_written_forwards_since() -> None:
    fqn = "cat.sch.fwd_w_since"
    older = str(uuid.uuid4())
    newer = str(uuid.uuid4())
    _seed_written_run(run_id=older, started_at=_BEFORE, fqn=fqn)
    _seed_written_run(run_id=newer, started_at=_AT_SINCE, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", since=_AT_SINCE)
    got = {r["id"] for r in rows}
    # A ``since=None`` substitution at the _by_written call site would
    # forward no lower bound and surface the older row too.
    assert got == {newer}


def test_runs_by_table_written_forwards_until() -> None:
    fqn = "cat.sch.fwd_w_until"
    inside = str(uuid.uuid4())
    on_bound = str(uuid.uuid4())
    _seed_written_run(run_id=inside, started_at=_AT_SINCE, fqn=fqn)
    _seed_written_run(run_id=on_bound, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", until=_AT_UNTIL)
    got = {r["id"] for r in rows}
    # An ``until=None`` substitution at the call site forwards no upper
    # bound and surfaces the on-bound row too.
    assert got == {inside}


def test_runs_by_table_written_forwards_limit() -> None:
    fqn = "cat.sch.fwd_w_limit"
    for i in range(3):
        _seed_written_run(
            run_id=str(uuid.uuid4()),
            started_at=_BASE + datetime.timedelta(minutes=i),
            fqn=fqn,
        )
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written", limit=1)
    # A ``limit=None`` substitution at the call site drops the cap.
    assert len(rows) == 1


def test_runs_by_table_read_forwards_since() -> None:
    fqn = "cat.sch.fwd_r_since"
    older = str(uuid.uuid4())
    newer = str(uuid.uuid4())
    _seed_read_run(run_id=older, started_at=_BEFORE, fqn=fqn)
    _seed_read_run(run_id=newer, started_at=_AT_SINCE, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", since=_AT_SINCE)
    got = {r["id"] for r in rows}
    # A ``since=None`` substitution at the _by_read call site forwards no
    # lower bound and surfaces the older row too.
    assert got == {newer}


def test_runs_by_table_read_forwards_until() -> None:
    fqn = "cat.sch.fwd_r_until"
    inside = str(uuid.uuid4())
    on_bound = str(uuid.uuid4())
    _seed_read_run(run_id=inside, started_at=_AT_SINCE, fqn=fqn)
    _seed_read_run(run_id=on_bound, started_at=_AT_UNTIL, fqn=fqn)
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", until=_AT_UNTIL)
    got = {r["id"] for r in rows}
    # An ``until=None`` substitution at the call site forwards no upper
    # bound and surfaces the on-bound row too.
    assert got == {inside}


def test_runs_by_table_read_forwards_limit() -> None:
    fqn = "cat.sch.fwd_r_limit"
    for i in range(3):
        _seed_read_run(
            run_id=str(uuid.uuid4()),
            started_at=_BASE + datetime.timedelta(minutes=i),
            fqn=fqn,
        )
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="read", limit=1)
    # A ``limit=None`` substitution at the call site drops the cap.
    assert len(rows) == 1


# ---------------------------------------------------------------------
# value-change axis sanity (guards the EXISTS subquery still matches)
# ---------------------------------------------------------------------


def test_by_written_value_change_axis_surfaces_run() -> None:
    fqn = "cat.sch.vc_only"
    vc_run = str(uuid.uuid4())
    _seed_run(run_id=vc_run, started_at=_BASE)
    with _factory()() as s:  # type: ignore[operator]
        # Backing op points elsewhere, so only the value-change axis can
        # surface this run for ``fqn``.
        op = AgentRunOperation(
            agent_run_id=vc_run,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.elsewhere",
            rows_affected=1,
            started_at=_BASE,
            finished_at=_BASE,
        )
        s.add(op)
        s.flush()
        s.add(
            LineageValueChange(
                run_id=vc_run,
                op_id=op.id,
                target_table=fqn,
                target_row_id="r0",
                target_column="email",
                old_value="a",
                new_value="b",
                created_at=_BASE,
            )
        )
        s.commit()
    rows = by_table.runs_by_table(_factory(), fqn=fqn, kind="written")
    assert {r["id"] for r in rows} == {vc_run}
