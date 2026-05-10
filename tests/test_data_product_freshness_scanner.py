"""Tests for the Phase-50.4 data-product freshness scanner.

Validates:

* Products without ``sla_minutes`` are skipped silently.
* Compliant products (latest write within SLA) emit nothing.
* Stale products emit one ``pointlessql.data_product.sla_violated``
  event and stamp ``last_alerted_at``.
* Re-alert suppression: a second tick within the suppression window
  emits no further events.

Uses :func:`monkeypatch.setattr` on the scanner module to inject
fake table-history fixtures, so the tests don't need a real Delta
table on disk.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import GovernanceEvent
from pointlessql.models.data_products import DataProduct
from pointlessql.services import data_product_freshness_scanner
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED,
)


def _seed_product(
    *,
    workspace_id: int = 1,
    catalog: str = "main",
    schema_name: str = "sales_gold",
    sla_minutes: int | None = 60,
    last_alerted_at: datetime.datetime | None = None,
) -> int:
    """Insert one ``data_products`` row and return its id."""
    factory = app.state.session_factory
    timestamp = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = DataProduct(
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema_name,
            steward_user_id=None,
            version="1.0.0",
            description="",
            sla_minutes=sla_minutes,
            contract_yaml_hash="0" * 64,
            contract_json="{}",
            last_loaded_at=timestamp,
            last_alerted_at=last_alerted_at,
            created_at=timestamp,
        )
        session.add(row)
        session.commit()
        return row.id


def _make_uc_mock(table_locations: list[str]) -> AsyncMock:
    """Return a mock ``UnityCatalogClient`` whose ``list_tables`` yields fixtures."""
    mock = AsyncMock()
    mock.list_tables = AsyncMock(
        return_value=[
            {"name": f"t_{i}", "storage_location": loc}
            for i, loc in enumerate(table_locations)
        ]
    )
    return mock


@pytest.mark.asyncio
async def test_skip_products_without_sla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Products with NULL ``sla_minutes`` are skipped before the IO branch."""
    _seed_product(sla_minutes=None)
    factory = app.state.session_factory
    uc = _make_uc_mock(["/tmp/fake"])

    called = False

    def _fake_latest(_loc: str) -> datetime.datetime | None:
        nonlocal called
        called = True
        return datetime.datetime.now(datetime.UTC)

    monkeypatch.setattr(
        data_product_freshness_scanner,
        "_latest_write_for_table",
        _fake_latest,
    )

    emitted = await data_product_freshness_scanner.scan_all(factory, uc)
    assert emitted == 0
    assert called is False  # the SLA-NULL product never reaches latest-write


@pytest.mark.asyncio
async def test_compliant_product_emits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A product whose newest write is within SLA emits nothing."""
    _seed_product(sla_minutes=60)
    factory = app.state.session_factory
    uc = _make_uc_mock(["/tmp/fake"])

    fresh_ts = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
    monkeypatch.setattr(
        data_product_freshness_scanner,
        "_latest_write_for_table",
        lambda _loc: fresh_ts,
    )

    emitted = await data_product_freshness_scanner.scan_all(factory, uc)
    assert emitted == 0

    with factory() as session:
        events = session.execute(select(GovernanceEvent)).scalars().all()
        assert events == []


@pytest.mark.asyncio
async def test_stale_product_emits_one_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """A product older than SLA emits one event + stamps ``last_alerted_at``."""
    product_id = _seed_product(sla_minutes=60)
    factory = app.state.session_factory
    uc = _make_uc_mock(["/tmp/fake"])

    stale_ts = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=4)
    monkeypatch.setattr(
        data_product_freshness_scanner,
        "_latest_write_for_table",
        lambda _loc: stale_ts,
    )

    emitted = await data_product_freshness_scanner.scan_all(factory, uc)
    assert emitted == 1

    with factory() as session:
        events = session.execute(select(GovernanceEvent)).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED
        row = session.get(DataProduct, product_id)
        assert row is not None
        assert row.last_alerted_at is not None


@pytest.mark.asyncio
async def test_re_alert_suppression(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two consecutive ticks within the suppress window emit one event."""
    _seed_product(sla_minutes=60)
    factory = app.state.session_factory
    uc = _make_uc_mock(["/tmp/fake"])

    stale_ts = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=4)
    monkeypatch.setattr(
        data_product_freshness_scanner,
        "_latest_write_for_table",
        lambda _loc: stale_ts,
    )

    first = await data_product_freshness_scanner.scan_all(
        factory, uc, re_alert_suppress_minutes=30
    )
    second = await data_product_freshness_scanner.scan_all(
        factory, uc, re_alert_suppress_minutes=30
    )
    assert first == 1
    assert second == 0

    with factory() as session:
        events = session.execute(select(GovernanceEvent)).scalars().all()
        assert len(events) == 1


@pytest.mark.asyncio
async def test_no_observable_history_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """When every table is unreadable the product is skipped (no false alert)."""
    _seed_product(sla_minutes=60)
    factory = app.state.session_factory
    uc = _make_uc_mock(["/tmp/fake1", "/tmp/fake2"])

    monkeypatch.setattr(
        data_product_freshness_scanner,
        "_latest_write_for_table",
        lambda _loc: None,
    )

    emitted = await data_product_freshness_scanner.scan_all(factory, uc)
    assert emitted == 0
