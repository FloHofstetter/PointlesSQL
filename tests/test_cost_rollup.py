"""Hourly cost rollup (Phase 146)."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductCostBucketHourly,
    DataProductQueryCost,
)
from pointlessql.services.cost import MeterContext, record_query_cost, roll_up_hourly_buckets


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product() -> int:
    contract = {"name": "p", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="ru",
            schema_name="run",
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(dp)
        session.commit()
        return int(dp.id)


def _record(dp_id: int, *, started_at: datetime.datetime, cost: Decimal) -> None:
    record_query_cost(
        _factory(),
        MeterContext(
            started_at=started_at,
            completed_at=started_at,
            duration_ms=10,
            estimated_cost=cost,
            bytes_scanned=1024,
            rows_returned=10,
            tables=[],
            principal_user_id=1,
            api_key_id=None,
            authoring_product_id=dp_id,
            consumer_product_id=None,
        ),
    )


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProductQueryCost).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_rollup_creates_bucket_for_hour() -> None:
    dp_id = _seed_product()
    moment = _now().replace(minute=15, second=0, microsecond=0)
    _record(dp_id, started_at=moment, cost=Decimal("0.10"))
    _record(dp_id, started_at=moment, cost=Decimal("0.05"))
    written = roll_up_hourly_buckets(
        _factory(),
        since=moment.replace(minute=0) - datetime.timedelta(minutes=1),
        until=moment + datetime.timedelta(minutes=30),
    )
    assert written == 1
    with _factory()() as session:
        bucket = session.query(DataProductCostBucketHourly).one()
        assert bucket.query_count == 2
        assert bucket.total_estimated_cost == Decimal("0.1500")


def test_rollup_is_idempotent_on_rerun() -> None:
    dp_id = _seed_product()
    moment = _now().replace(minute=10, second=0, microsecond=0)
    _record(dp_id, started_at=moment, cost=Decimal("1"))
    window_start = moment.replace(minute=0)
    window_end = window_start + datetime.timedelta(hours=1)
    roll_up_hourly_buckets(_factory(), since=window_start, until=window_end)
    roll_up_hourly_buckets(_factory(), since=window_start, until=window_end)
    with _factory()() as session:
        rows = session.query(DataProductCostBucketHourly).all()
        assert len(rows) == 1
        assert rows[0].query_count == 1


def test_rollup_skips_rows_without_authoring_product() -> None:
    moment = _now().replace(minute=20, second=0, microsecond=0)
    record_query_cost(
        _factory(),
        MeterContext(
            started_at=moment,
            completed_at=moment,
            duration_ms=10,
            estimated_cost=Decimal("0.5"),
            bytes_scanned=None,
            rows_returned=None,
            tables=[],
            principal_user_id=None,
            api_key_id=None,
            authoring_product_id=None,
            consumer_product_id=None,
        ),
    )
    written = roll_up_hourly_buckets(
        _factory(),
        since=moment - datetime.timedelta(hours=1),
        until=moment + datetime.timedelta(hours=1),
    )
    assert written == 0
    with _factory()() as session:
        assert session.query(DataProductCostBucketHourly).count() == 0
