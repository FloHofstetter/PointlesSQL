"""Mesh-health-full dashboard aggregator (Phase 146)."""

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
from pointlessql.services.cost import (
    cost_by_consumer,
    cost_by_product,
    mesh_health_full,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product(catalog: str, schema: str) -> int:
    contract = {"name": "p", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
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


def _seed_bucket(
    dp_id: int,
    *,
    cost: Decimal,
    queries: int,
    consumer_user_id: int | None = None,
) -> None:
    moment = _now().replace(minute=0, second=0, microsecond=0)
    with _factory()() as session:
        session.add(
            DataProductCostBucketHourly(
                bucket_hour=moment,
                data_product_id=dp_id,
                consumer_user_id=consumer_user_id,
                query_count=queries,
                total_duration_ms=queries * 100,
                total_estimated_cost=cost,
                total_bytes_scanned=queries * 1024,
            )
        )
        session.commit()


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProductQueryCost).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_cost_by_product_sums_buckets() -> None:
    a = _seed_product("mh", "alpha")
    b = _seed_product("mh", "beta")
    _seed_bucket(a, cost=Decimal("3.00"), queries=10)
    _seed_bucket(b, cost=Decimal("1.50"), queries=5)
    rows = cost_by_product(_factory(), workspace_id=1)
    assert len(rows) == 2
    refs = {row["ref"] for row in rows}
    assert refs == {"mh.alpha", "mh.beta"}
    top = rows[0]
    assert top["ref"] == "mh.alpha"
    assert float(top["total_estimated_cost"]) == pytest.approx(3.0)


def test_cost_by_consumer_groups_by_user() -> None:
    a = _seed_product("mh", "two_users")
    _seed_bucket(a, cost=Decimal("1"), queries=2, consumer_user_id=1)
    _seed_bucket(a, cost=Decimal("2"), queries=4, consumer_user_id=2)
    rows = cost_by_consumer(_factory(), workspace_id=1)
    assert {row["consumer_user_id"] for row in rows} == {1, 2}
    assert rows[0]["query_count"] >= rows[1]["query_count"]


def test_mesh_health_full_carries_base_payload() -> None:
    _seed_product("mh", "with_bucket")
    payload = mesh_health_full(_factory(), workspace_id=1)
    assert "products" in payload
    assert "summary" in payload
    assert "per_domain" in payload
    assert "cost_trend" in payload
    assert "top_consumers" in payload


def test_mesh_health_full_buckets_per_domain() -> None:
    _seed_product("mh", "domain_test")
    payload = mesh_health_full(_factory(), workspace_id=1)
    per_domain = payload["per_domain"]
    assert isinstance(per_domain, dict)
    for entry in per_domain.values():
        assert "green" in entry
        assert "red" in entry
        assert "unknown" in entry


def test_cost_by_product_respects_time_window() -> None:
    a = _seed_product("mh", "windowed")
    _seed_bucket(a, cost=Decimal("5"), queries=1)
    far_future = _now() + datetime.timedelta(days=14)
    rows = cost_by_product(
        _factory(),
        workspace_id=1,
        since=far_future,
        until=far_future + datetime.timedelta(days=1),
    )
    assert rows == []


def test_empty_workspace_returns_empty_lists() -> None:
    rows = cost_by_product(_factory(), workspace_id=1)
    assert rows == []
    assert cost_by_consumer(_factory(), workspace_id=1) == []


def test_top_consumers_truncated_to_ten() -> None:
    a = _seed_product("mh", "ten_users")
    for uid in range(1, 12):
        _seed_bucket(a, cost=Decimal("0.1"), queries=uid, consumer_user_id=uid)
    payload = mesh_health_full(_factory(), workspace_id=1)
    assert len(payload["top_consumers"]) <= 10
