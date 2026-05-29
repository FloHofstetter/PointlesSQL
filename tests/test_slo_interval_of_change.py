"""Interval-of-change SLO measurement (G1)."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.slo._interval_of_change import (
    measure_interval_of_change,
    verdict_from_measurement,
)


def _factory():
    return app.state.session_factory


def _seed_product(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract: dict[str, Any] = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash=f"{catalog}_{schema}".ljust(64, "0"),
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_op() -> int:
    """Create one AgentRun + AgentRunOperation, return op_id."""
    import uuid

    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            notebook_path="seed.py",
            status="running",
            started_at=now,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run.id,
            ordinal=0,
            op_name="update",
            params_json="{}",
            started_at=now,
        )
        session.add(op)
        session.commit()
        return int(op.id)


def _seed_writes(product_id: int, intervals_minutes: list[int]) -> None:
    """Seed write events spaced by the given inter-write intervals."""
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    timestamps = [base]
    for delta in intervals_minutes:
        timestamps.append(timestamps[-1] + datetime.timedelta(minutes=delta))
    op_id = _seed_op()
    with _factory()() as session:
        for ts in timestamps:
            session.add(
                DataProductContractEvent(
                    agent_run_operation_id=op_id,
                    data_product_id=product_id,
                    outcome="compliant",
                    details_json="{}",
                    created_at=ts,
                )
            )
        session.commit()


def test_no_writes_returns_none() -> None:
    dp = _seed_product("ioc", "empty")
    assert measure_interval_of_change(_factory(), data_product_id=dp) is None


def test_single_write_returns_none() -> None:
    dp = _seed_product("ioc", "single")
    _seed_writes(dp, [])
    assert measure_interval_of_change(_factory(), data_product_id=dp) is None


def test_two_writes_returns_single_interval() -> None:
    dp = _seed_product("ioc", "double")
    _seed_writes(dp, [60])
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.median_minutes == 60.0
    assert m.sample_size == 1


def test_median_of_three_intervals() -> None:
    dp = _seed_product("ioc", "triple")
    _seed_writes(dp, [30, 60, 90])
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.median_minutes == 60.0


def test_p95_is_upper_tail() -> None:
    dp = _seed_product("ioc", "tail")
    _seed_writes(dp, [10, 10, 10, 10, 1000])
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.p95_minutes > m.median_minutes


def test_window_cap_respects_recent() -> None:
    dp = _seed_product("ioc", "windowed")
    _seed_writes(dp, [10] * 99)
    m = measure_interval_of_change(_factory(), data_product_id=dp, window=10)
    assert m is not None
    assert m.sample_size == 9


def test_window_below_two_raises() -> None:
    dp = _seed_product("ioc", "winraise")
    with pytest.raises(ValueError):
        measure_interval_of_change(_factory(), data_product_id=dp, window=1)


def test_verdict_pass_when_under_lte_target() -> None:
    m_dp = _seed_product("ioc", "verdict_pass")
    _seed_writes(m_dp, [10, 10])
    measurement = measure_interval_of_change(_factory(), data_product_id=m_dp)
    verdict, _ = verdict_from_measurement(
        measurement, target_value=60.0, comparator="lte"
    )
    assert verdict == "pass"


def test_verdict_fail_when_over_lte_target() -> None:
    m_dp = _seed_product("ioc", "verdict_fail")
    _seed_writes(m_dp, [200, 200])
    measurement = measure_interval_of_change(_factory(), data_product_id=m_dp)
    verdict, _ = verdict_from_measurement(
        measurement, target_value=60.0, comparator="lte"
    )
    assert verdict == "fail"


def test_verdict_unmeasured_when_no_samples() -> None:
    verdict, detail = verdict_from_measurement(
        None, target_value=60.0, comparator="lte"
    )
    assert verdict == "unmeasured"
    assert "reason" in detail
