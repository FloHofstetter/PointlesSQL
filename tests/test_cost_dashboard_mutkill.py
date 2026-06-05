"""Mutation-killing tests for the mesh-cost dashboard aggregators.

Seeds hourly cost buckets + products and pins the per-product /
per-consumer rollups (window filtering, summation, ref mapping,
Decimal->float, descending sort) and the per-domain band grouping.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductCostBucketHourly, User
from pointlessql.services.cost._dashboard import (
    _aggregate_per_domain,
    cost_by_consumer,
    cost_by_product,
)

_T0 = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
_UNTIL = datetime.datetime(2026, 1, 2, 0, 0, tzinfo=datetime.UTC)


def _factory() -> Any:
    return app.state.session_factory


@pytest.fixture(autouse=True)
def _wipe() -> Any:
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProduct).delete()
        session.commit()


def _mk_product(catalog: str, schema: str, *, workspace_id: int = 1) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps({"name": "p", "version": "1.0.0", "tables": []}),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.commit()
        return int(dp.id)


def _bucket(
    *,
    product_id: int,
    when: datetime.datetime,
    cost: str = "0",
    qc: int = 0,
    dur: int = 0,
    bytes_: int = 0,
    consumer: int | None = None,
) -> None:
    with _factory()() as session:
        session.add(
            DataProductCostBucketHourly(
                bucket_hour=when,
                data_product_id=product_id,
                consumer_user_id=consumer,
                query_count=qc,
                total_duration_ms=dur,
                total_estimated_cost=Decimal(cost),
                total_bytes_scanned=bytes_,
            )
        )
        session.commit()


def _user_id() -> int:
    with _factory()() as session:
        return int(session.scalars(select(User.id)).first())


# --- cost_by_product ------------------------------------------------------


def test_cost_by_product_aggregates_sums_and_sorts() -> None:
    a = _mk_product("ca", "sa")
    b = _mk_product("cb", "sb")
    _bucket(
        product_id=a, when=_T0 + datetime.timedelta(hours=6), cost="1.5", qc=3, dur=10, bytes_=100
    )
    _bucket(
        product_id=a, when=_T0 + datetime.timedelta(hours=12), cost="2.5", qc=2, dur=20, bytes_=200
    )
    _bucket(
        product_id=b, when=_T0 + datetime.timedelta(hours=1), cost="10.0", qc=1, dur=5, bytes_=50
    )

    out = cost_by_product(_factory(), workspace_id=1, since=_T0, until=_UNTIL)
    # Sorted by total cost descending: b (10.0) then a (4.0).
    assert [e["ref"] for e in out] == ["cb.sb", "ca.sa"]
    a_entry = next(e for e in out if e["ref"] == "ca.sa")
    assert a_entry["data_product_id"] == a
    assert a_entry["query_count"] == 5
    assert a_entry["total_duration_ms"] == 30
    assert a_entry["total_bytes_scanned"] == 300
    assert a_entry["total_estimated_cost"] == 4.0
    assert isinstance(a_entry["total_estimated_cost"], float)


def test_cost_by_product_excludes_out_of_window_buckets() -> None:
    a = _mk_product("ca", "sa")
    _bucket(product_id=a, when=_T0 + datetime.timedelta(hours=6), cost="1.0", qc=1)
    _bucket(product_id=a, when=_UNTIL, cost="99.0", qc=99)  # == until -> excluded
    _bucket(
        product_id=a, when=_T0 - datetime.timedelta(hours=1), cost="88.0", qc=88
    )  # before start

    out = cost_by_product(_factory(), workspace_id=1, since=_T0, until=_UNTIL)
    assert len(out) == 1
    assert out[0]["query_count"] == 1
    assert out[0]["total_estimated_cost"] == 1.0


def test_cost_by_product_unknown_ref_for_foreign_workspace_product() -> None:
    other = _mk_product("cz", "sz", workspace_id=2)
    _bucket(product_id=other, when=_T0 + datetime.timedelta(hours=2), cost="3.0", qc=1)

    out = cost_by_product(_factory(), workspace_id=1, since=_T0, until=_UNTIL)
    assert len(out) == 1
    assert out[0]["ref"] == "unknown"
    assert out[0]["data_product_id"] == other


# --- cost_by_consumer -----------------------------------------------------


def test_cost_by_consumer_groups_and_sorts_by_query_count() -> None:
    a = _mk_product("ca", "sa")
    uid = _user_id()
    # consumer `uid`: 5 queries; anonymous (None): 2 queries.
    _bucket(product_id=a, when=_T0 + datetime.timedelta(hours=1), cost="1.0", qc=3, consumer=uid)
    _bucket(product_id=a, when=_T0 + datetime.timedelta(hours=2), cost="1.0", qc=2, consumer=uid)
    _bucket(product_id=a, when=_T0 + datetime.timedelta(hours=3), cost="9.0", qc=2, consumer=None)

    out = cost_by_consumer(_factory(), workspace_id=1, since=_T0, until=_UNTIL)
    # Sorted by query_count descending: uid (5) before None (2).
    assert [e["consumer_user_id"] for e in out] == [uid, None]
    assert out[0]["query_count"] == 5
    assert out[0]["total_estimated_cost"] == 2.0
    assert out[1]["consumer_user_id"] is None
    assert out[1]["query_count"] == 2


# --- _aggregate_per_domain ------------------------------------------------


def test_aggregate_per_domain_counts_bands_under_uncategorised() -> None:
    p = _mk_product("ca", "sa")
    base: dict[str, Any] = {
        "products": [
            {"data_product_id": p, "band": "green"},
            {"data_product_id": p, "band": "green"},
            {"data_product_id": p, "band": "red"},
            {"data_product_id": p, "band": "amber"},  # neither green nor red -> unknown
        ]
    }
    out = _aggregate_per_domain(_factory(), 1, base)
    # DataProduct exposes domain_id (not `domain`), so everything lands
    # under the uncategorised bucket.
    assert set(out) == {"uncategorised"}
    bucket = out["uncategorised"]
    assert bucket == {"green": 2, "red": 1, "unknown": 1, "total": 4}


def test_aggregate_per_domain_empty_products() -> None:
    out = _aggregate_per_domain(_factory(), 1, {"products": []})
    assert out == {}
