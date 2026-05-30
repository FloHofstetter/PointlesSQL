"""Quota enforcement (Phase 146)."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import QuotaExceededError
from pointlessql.models import (
    DataProduct,
    DataProductCostBucketHourly,
    DataProductPolicy,
)
from pointlessql.services.cost import check_quota, resolve_quota_mode
from pointlessql.services.governance._policy import set_product_policy


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(minute=0, second=0, microsecond=0)


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
    count: int,
    consumer_user_id: int | None = None,
    hour_offset: int = 0,
) -> None:
    moment = _now() - datetime.timedelta(hours=hour_offset)
    with _factory()() as session:
        session.add(
            DataProductCostBucketHourly(
                bucket_hour=moment,
                data_product_id=dp_id,
                consumer_user_id=consumer_user_id,
                query_count=count,
                total_duration_ms=count * 100,
                total_estimated_cost=cost,
                total_bytes_scanned=count * 1024,
            )
        )
        session.commit()


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_off_mode_returns_no_check() -> None:
    dp_id = _seed_product("q", "off")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"quota_enforcement": "off"},
    )
    result = check_quota(
        _factory(), consumer_user_id=1, data_product_id=dp_id
    )
    assert result.mode == "off"
    assert result.breached is False


def test_warn_mode_returns_outcome_without_raising() -> None:
    dp_id = _seed_product("q", "warn")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "warn",
            "max_cost_per_day": Decimal("5"),
        },
    )
    _seed_bucket(dp_id, cost=Decimal("10"), count=1)
    result = check_quota(
        _factory(), consumer_user_id=1, data_product_id=dp_id
    )
    assert result.mode == "warn"
    assert result.breached is True
    assert result.offending_metric == "cost_per_day"


def test_strict_mode_raises_quota_exceeded() -> None:
    dp_id = _seed_product("q", "strict_cost")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "strict",
            "max_cost_per_day": Decimal("5"),
        },
    )
    _seed_bucket(dp_id, cost=Decimal("10"), count=1)
    with pytest.raises(QuotaExceededError) as info:
        check_quota(
            _factory(), consumer_user_id=1, data_product_id=dp_id
        )
    assert info.value.status_code == 429
    assert info.value.metric == "cost_per_day"


def test_strict_mode_blocks_on_queries_per_hour() -> None:
    dp_id = _seed_product("q", "strict_queries")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "strict",
            "max_queries_per_hour": 5,
        },
    )
    _seed_bucket(dp_id, cost=Decimal("1"), count=10)
    with pytest.raises(QuotaExceededError) as info:
        check_quota(
            _factory(), consumer_user_id=None, data_product_id=dp_id
        )
    assert info.value.metric == "queries_per_hour"


def test_below_limit_passes_without_breach() -> None:
    dp_id = _seed_product("q", "below_limit")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "strict",
            "max_cost_per_day": Decimal("100"),
            "max_queries_per_hour": 100,
        },
    )
    _seed_bucket(dp_id, cost=Decimal("0.50"), count=1)
    result = check_quota(
        _factory(), consumer_user_id=1, data_product_id=dp_id
    )
    assert result.breached is False
    assert result.observed_cost_today == Decimal("0.50")


def test_old_hour_does_not_count_toward_current_hour() -> None:
    dp_id = _seed_product("q", "stale_hour")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "strict",
            "max_queries_per_hour": 5,
        },
    )
    _seed_bucket(dp_id, cost=Decimal("1"), count=20, hour_offset=2)
    result = check_quota(
        _factory(), consumer_user_id=None, data_product_id=dp_id
    )
    assert result.breached is False


def test_resolve_quota_mode_returns_off_when_unset() -> None:
    dp_id = _seed_product("q", "resolve")
    mode, limits = resolve_quota_mode(
        _factory(), data_product_id=dp_id
    )
    assert mode == "off"
    assert limits["max_cost_per_day"] is None


def test_resolve_quota_mode_respects_product_override() -> None:
    dp_id = _seed_product("q", "override")
    set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={
            "quota_enforcement": "strict",
            "max_cost_per_day": Decimal("42.50"),
        },
    )
    mode, limits = resolve_quota_mode(
        _factory(), data_product_id=dp_id
    )
    assert mode == "strict"
    assert limits["max_cost_per_day"] == Decimal("42.50")
