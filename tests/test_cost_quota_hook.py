"""Quota check wired into the PQL before-read hook registry."""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator
from decimal import Decimal

import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import QuotaExceededError
from pointlessql.models import (
    DataProduct,
    DataProductCostBucketHourly,
    DataProductPolicy,
)
from pointlessql.pql._hooks import HookContext, run_before_read
from pointlessql.services.cost._bootstrap import (
    register_cost_hooks,
    reset_for_tests,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _wipe() -> None:
    with _factory()() as session:
        session.query(DataProductCostBucketHourly).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProduct).delete()
        session.commit()


def _seed_product(quota_mode: str = "off", queries_per_hour: int | None = None) -> int:
    contract = {
        "name": "hook.quota",
        "version": "1.0.0",
        "description": "",
        "catalog": "hook",
        "schema_name": "quota",
        "tables": [],
    }
    with _factory()() as session:
        product = DataProduct(
            workspace_id=1,
            catalog_name="hook",
            schema_name="quota",
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(product)
        session.flush()
        policy = DataProductPolicy(
            data_product_id=int(product.id),
            quota_enforcement=quota_mode,
            max_queries_per_hour=queries_per_hour,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(policy)
        session.commit()
        return int(product.id)


def _seed_bucket(data_product_id: int, query_count: int) -> None:
    hour = _now().replace(minute=0, second=0, microsecond=0)
    with _factory()() as session:
        session.add(
            DataProductCostBucketHourly(
                bucket_hour=hour,
                data_product_id=data_product_id,
                consumer_user_id=None,
                query_count=query_count,
                total_duration_ms=0,
                total_estimated_cost=Decimal("0"),
                total_bytes_scanned=0,
            )
        )
        session.commit()


@pytest.fixture
def quota_hook_env() -> Iterator[None]:
    _wipe()
    reset_for_tests()
    with HookContext():
        register_cost_hooks(_factory())
        yield
    reset_for_tests()
    _wipe()


def test_register_cost_hooks_is_idempotent(quota_hook_env: None) -> None:
    from pointlessql.pql._hooks import registered_counts

    before = registered_counts()["before_read"]
    register_cost_hooks(_factory())
    assert registered_counts()["before_read"] == before


def test_off_mode_lets_read_through(quota_hook_env: None) -> None:
    product_id = _seed_product(quota_mode="off")
    run_before_read(
        {
            "full_name": "hook.quota.foo",
            "principal": {"id": 1, "email": "a@b.test"},
            "authoring_product_id": product_id,
            "workspace_id": 1,
        }
    )


def test_strict_breach_raises_quota_exceeded(quota_hook_env: None) -> None:
    product_id = _seed_product(quota_mode="strict", queries_per_hour=1)
    _seed_bucket(product_id, query_count=2)
    with pytest.raises(QuotaExceededError):
        run_before_read(
            {
                "full_name": "hook.quota.foo",
                "principal": {"id": 1, "email": "a@b.test"},
                "authoring_product_id": product_id,
                "workspace_id": 1,
            }
        )


def test_missing_authoring_product_skips_hook(quota_hook_env: None) -> None:
    run_before_read(
        {
            "full_name": "no.product.here",
            "principal": {"id": 1, "email": "a@b.test"},
            "workspace_id": 1,
        }
    )
