"""Runtime SLO measurers (140) — timeliness/precision/availability/performance."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductAvailabilityProbe,
    DataProductQueryPerfSample,
    DataProductStatistics,
)
from pointlessql.services.slo import _runtime as runtime_slo


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


def test_timeliness_unmeasured_without_columns() -> None:
    dp = _seed_product("rt1", "t1")
    verdict, _ = runtime_slo.measure_timeliness(
        _factory(),
        data_product_id=dp,
        event_time_col=None,
        processing_time_col=None,
        target_value=60.0,
    )
    assert verdict == "unmeasured"


def test_timeliness_unmeasured_with_columns_returns_declaration_sentinel() -> None:
    dp = _seed_product("rt2", "t2")
    verdict, detail = runtime_slo.measure_timeliness(
        _factory(),
        data_product_id=dp,
        event_time_col="event_time",
        processing_time_col="processing_time",
        target_value=60.0,
    )
    assert verdict == "unmeasured"
    assert detail["event_time_col"] == "event_time"


def test_precision_unmeasured_without_snapshot() -> None:
    dp = _seed_product("rt3", "t3")
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(),
        data_product_id=dp,
        table_name=None,
        target_value=0.05,
    )
    assert verdict == "unmeasured"


def test_precision_passes_when_null_ratio_under_target() -> None:
    dp = _seed_product("rt4", "t4")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp,
                table_name="t4",
                row_count=100,
                shape_json=json.dumps({"null_ratio_max": 0.01}),
                created_at=now,
            )
        )
        session.commit()
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(),
        data_product_id=dp,
        table_name=None,
        target_value=0.05,
    )
    assert verdict == "pass"


def test_precision_fails_when_null_ratio_over_target() -> None:
    dp = _seed_product("rt5", "t5")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp,
                table_name="t5",
                row_count=100,
                shape_json=json.dumps({"null_ratio_max": 0.10}),
                created_at=now,
            )
        )
        session.commit()
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(),
        data_product_id=dp,
        table_name=None,
        target_value=0.05,
    )
    assert verdict == "fail"


def test_availability_unmeasured_without_probes() -> None:
    dp = _seed_product("rt6", "t6")
    verdict, _ = runtime_slo.measure_availability(_factory(), data_product_id=dp, target_value=99.0)
    assert verdict == "unmeasured"


def test_availability_passes_when_above_target() -> None:
    dp = _seed_product("rt7", "t7")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for _ in range(99):
            session.add(
                DataProductAvailabilityProbe(
                    data_product_id=dp,
                    output_port_id=None,
                    port_kind="sql",
                    probed_at=now,
                    latency_ms=5,
                    status="ok",
                )
            )
        session.add(
            DataProductAvailabilityProbe(
                data_product_id=dp,
                output_port_id=None,
                port_kind="sql",
                probed_at=now,
                latency_ms=None,
                status="fail",
            )
        )
        session.commit()
    verdict, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=95.0
    )
    assert verdict == "pass"
    assert detail["observed_percent"] == 99.0


def test_availability_fails_when_below_target() -> None:
    dp = _seed_product("rt8", "t8")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for _ in range(10):
            session.add(
                DataProductAvailabilityProbe(
                    data_product_id=dp,
                    output_port_id=None,
                    port_kind="sql",
                    probed_at=now,
                    latency_ms=5,
                    status="ok",
                )
            )
        for _ in range(10):
            session.add(
                DataProductAvailabilityProbe(
                    data_product_id=dp,
                    output_port_id=None,
                    port_kind="sql",
                    probed_at=now,
                    latency_ms=None,
                    status="fail",
                )
            )
        session.commit()
    verdict, _ = runtime_slo.measure_availability(_factory(), data_product_id=dp, target_value=95.0)
    assert verdict == "fail"


def test_performance_unmeasured_without_samples() -> None:
    dp = _seed_product("rt9", "t9")
    verdict, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=1000.0
    )
    assert verdict == "unmeasured"


def test_performance_passes_when_p95_under_target() -> None:
    dp = _seed_product("rt10", "t10")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for i in range(50):
            session.add(
                DataProductQueryPerfSample(
                    data_product_id=dp,
                    table_name="t10",
                    started_at=now,
                    duration_ms=100 + i,
                    status="ok",
                )
            )
        session.commit()
    verdict, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=1000.0
    )
    assert verdict == "pass"
    assert detail["observed_p95_ms"] < 1000


def test_dispatch_unknown_kind_raises() -> None:
    dp = _seed_product("rt11", "t11")
    with pytest.raises(ValueError):
        runtime_slo.measure_runtime_kind(
            _factory(),
            kind="bogus",
            data_product_id=dp,
            target_value=0.0,
            comparator="lte",
        )


def test_dispatch_routes_to_availability() -> None:
    dp = _seed_product("rt12", "t12")
    verdict, _ = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=99.0,
        comparator="gte",
    )
    assert verdict == "unmeasured"
