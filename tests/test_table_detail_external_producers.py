"""Tests for the table-detail "External producers" surface.

wires inbound lineage edges into the existing
``components/lineage_card.html`` block on the table-detail page.
The pure-helper test here exercises the
``_external_producers_for_table`` aggregator that drives the
template's new amber-badged section.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete

from pointlessql.api.catalog_html_routes import _external_producers_for_table
from pointlessql.api.main import app
from pointlessql.models import LineageColumnMap


def _wipe_external_edges() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.execute(delete(LineageColumnMap).where(LineageColumnMap.producer.is_not(None)))
        session.commit()


@pytest.fixture(autouse=True)
def _wipe_around() -> None:
    _wipe_external_edges()
    yield
    _wipe_external_edges()


def _seed_inbound_edge(
    *,
    target_table: str,
    target_column: str,
    source_table: str,
    producer: str,
    when: dt.datetime,
) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                workspace_id=1,
                run_id=None,
                op_id=None,
                source_table=source_table,
                source_column="x",
                target_table=target_table,
                target_column=target_column,
                transform_kind="identity",
                producer=producer,
                external_event_id="evt",
                created_at=when,
            )
        )
        session.commit()


def test_no_inbound_edges_returns_empty_list() -> None:
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert rows == []


def test_one_producer_one_source_table() -> None:
    when = dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC)
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="user_id",
        source_table="kafka.events.signups",
        producer="kafka.events.us-east",
        when=when,
    )
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["producer"] == "kafka.events.us-east"
    assert row["source_tables"] == ["kafka.events.signups"]
    seen = row["last_seen_at"]
    assert seen is not None
    # SQLite returns naive datetimes; PG returns tz-aware.  Compare
    # the wall-clock pieces only so the test stays dialect-portable.
    assert (seen.year, seen.month, seen.day, seen.hour) == (
        when.year,
        when.month,
        when.day,
        when.hour,
    )


def test_two_producers_ordered_by_last_seen_desc() -> None:
    older = dt.datetime(2026, 5, 5, 0, 0, tzinfo=dt.UTC)
    newer = dt.datetime(2026, 5, 6, 0, 0, tzinfo=dt.UTC)
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="a",
        source_table="src.a",
        producer="prod-old",
        when=older,
    )
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="b",
        source_table="src.b",
        producer="prod-new",
        when=newer,
    )
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert [r["producer"] for r in rows] == ["prod-new", "prod-old"]


def test_producer_with_multiple_source_tables_dedupes() -> None:
    when = dt.datetime(2026, 5, 6, 1, 0, tzinfo=dt.UTC)
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="a",
        source_table="src.t1",
        producer="prod-multi",
        when=when,
    )
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="b",
        source_table="src.t2",
        producer="prod-multi",
        when=when,
    )
    _seed_inbound_edge(
        target_table="main.silver.events",
        target_column="c",
        source_table="src.t1",  # repeat
        producer="prod-multi",
        when=when,
    )
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert len(rows) == 1
    assert sorted(rows[0]["source_tables"]) == ["src.t1", "src.t2"]


def test_internal_edges_excluded() -> None:
    """An internal edge (producer IS NULL) must not appear in external_producers."""
    when = dt.datetime(2026, 5, 6, 0, 0, tzinfo=dt.UTC)
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                workspace_id=1,
                run_id=None,
                op_id=None,
                source_table="main.bronze.events",
                source_column="x",
                target_table="main.silver.events",
                target_column="x",
                transform_kind="identity",
                producer=None,
                external_event_id=None,
                created_at=when,
            )
        )
        session.commit()
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert rows == []


def test_other_target_tables_excluded() -> None:
    when = dt.datetime(2026, 5, 6, 1, 0, tzinfo=dt.UTC)
    _seed_inbound_edge(
        target_table="main.silver.other",
        target_column="x",
        source_table="src.a",
        producer="other-prod",
        when=when,
    )
    rows = _external_producers_for_table(
        "main.silver.events", session_factory=app.state.session_factory
    )
    assert rows == []
