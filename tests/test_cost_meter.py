"""Per-query cost meter (Phase 146)."""

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
from pointlessql.services.cost import MeterContext, record_query_cost


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product() -> int:
    contract = {"name": "p", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="meter",
            schema_name="t",
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


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(DataProductQueryCost).delete()
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_record_query_cost_persists_row() -> None:
    dp_id = _seed_product()
    rid = record_query_cost(
        _factory(),
        MeterContext(
            started_at=_now(),
            completed_at=_now(),
            duration_ms=50,
            estimated_cost=Decimal("0.05"),
            bytes_scanned=1024,
            rows_returned=10,
            tables=["meter.t.events"],
            principal_user_id=1,
            api_key_id=None,
            authoring_product_id=dp_id,
            consumer_product_id=None,
        ),
    )
    assert rid > 0
    with _factory()() as session:
        row = session.get(DataProductQueryCost, rid)
        assert row is not None
        assert row.authoring_product_id == dp_id
        assert json.loads(row.table_list_json) == ["meter.t.events"]


def test_meter_handles_no_table_attribution() -> None:
    record_query_cost(
        _factory(),
        MeterContext(
            started_at=_now(),
            completed_at=None,
            duration_ms=None,
            estimated_cost=Decimal("0"),
            bytes_scanned=None,
            rows_returned=None,
            tables=[],
            principal_user_id=None,
            api_key_id=None,
            authoring_product_id=None,
            consumer_product_id=None,
            error_class="LookupError",
        ),
    )
    with _factory()() as session:
        assert session.query(DataProductQueryCost).count() == 1
        row = session.query(DataProductQueryCost).one()
        assert row.error_class == "LookupError"
        assert row.authoring_product_id is None


def test_meter_supports_float_cost_input() -> None:
    dp_id = _seed_product()
    record_query_cost(
        _factory(),
        MeterContext(
            started_at=_now(),
            completed_at=_now(),
            duration_ms=10,
            estimated_cost=0.42,
            bytes_scanned=None,
            rows_returned=None,
            tables=[],
            principal_user_id=1,
            api_key_id=None,
            authoring_product_id=dp_id,
            consumer_product_id=None,
        ),
    )
    with _factory()() as session:
        row = session.query(DataProductQueryCost).one()
        assert Decimal(str(row.estimated_cost)) == Decimal("0.42")
