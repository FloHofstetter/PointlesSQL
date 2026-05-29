"""Phase 133 — event-port subscription substrate (Delta CDF runtime deferred)."""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.config import EventPortSettings
from pointlessql.models import (
    DataProduct,
    DataProductEventDelivery,
    DataProductOutputPort,
)
from pointlessql.services import event_port as event_port_service


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
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
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_output_port(dp_id: int, *, kind: str = "event", name: str = "stream") -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        port = DataProductOutputPort(
            data_product_id=dp_id,
            name=name,
            kind=kind,
            format="ndjson" if kind == "event" else "parquet",
            description="",
            created_at=now,
        )
        session.add(port)
        session.commit()
        return port.id


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


def test_event_port_settings_defaults_off() -> None:
    settings = EventPortSettings()
    assert settings.enabled is False
    assert settings.default_format == "ndjson"
    assert settings.cdf_max_versions_per_pump == 100


# ---------------------------------------------------------------------------
# create + validate
# ---------------------------------------------------------------------------


def test_create_subscription_on_event_port_succeeds() -> None:
    dp_id = _seed_dp("ev", "ok")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="orders",
        consumer_label="downstream-ml",
    )
    assert sub["table_name"] == "orders"
    assert sub["consumer_label"] == "downstream-ml"
    assert sub["status"] == "active"
    assert sub["position"] == {"version": 0, "row_offset": 0}


def test_create_rejects_non_event_port() -> None:
    dp_id = _seed_dp("ev", "file")
    port_id = _seed_output_port(dp_id, kind="file", name="parquet-export")
    with pytest.raises(ValueError):
        event_port_service.create_subscription(
            _factory(),
            data_product_id=dp_id,
            output_port_id=port_id,
            table_name="orders",
            consumer_label="downstream",
        )


def test_create_rejects_cross_product_port() -> None:
    dp1 = _seed_dp("ev", "p1")
    dp2 = _seed_dp("ev", "p2")
    port_id = _seed_output_port(dp1)
    with pytest.raises(ValueError):
        event_port_service.create_subscription(
            _factory(),
            data_product_id=dp2,
            output_port_id=port_id,
            table_name="orders",
            consumer_label="downstream",
        )


def test_create_rejects_duplicate_identity() -> None:
    dp_id = _seed_dp("ev", "dup")
    port_id = _seed_output_port(dp_id)
    event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="orders",
        consumer_label="x",
    )
    with pytest.raises(ValueError):
        event_port_service.create_subscription(
            _factory(),
            data_product_id=dp_id,
            output_port_id=port_id,
            table_name="orders",
            consumer_label="x",
        )


def test_create_with_start_version() -> None:
    dp_id = _seed_dp("ev", "start")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="late-joiner",
        start_version=42,
    )
    assert sub["position"]["version"] == 42


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


def test_pause_and_resume_round_trip() -> None:
    dp_id = _seed_dp("ev", "pr")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    paused = event_port_service.pause_subscription(_factory(), subscription_id=sub["id"])
    assert paused["status"] == "paused"
    resumed = event_port_service.resume_subscription(_factory(), subscription_id=sub["id"])
    assert resumed["status"] == "active"


def test_delete_subscription_returns_bool() -> None:
    dp_id = _seed_dp("ev", "del")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    assert event_port_service.delete_subscription(_factory(), subscription_id=sub["id"])
    assert not event_port_service.delete_subscription(_factory(), subscription_id=sub["id"])


# ---------------------------------------------------------------------------
# cursor math
# ---------------------------------------------------------------------------


def test_advance_position_forward_only() -> None:
    dp_id = _seed_dp("ev", "adv")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    moved = event_port_service.advance_position(
        _factory(), subscription_id=sub["id"], to_version=5
    )
    assert moved["position"]["version"] == 5
    assert moved["last_delivered_at"] is not None
    with pytest.raises(ValueError):
        event_port_service.advance_position(
            _factory(), subscription_id=sub["id"], to_version=3
        )


def test_rewind_subscription_moves_back() -> None:
    dp_id = _seed_dp("ev", "rew")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    event_port_service.advance_position(
        _factory(), subscription_id=sub["id"], to_version=10
    )
    rewound = event_port_service.rewind_subscription(
        _factory(), subscription_id=sub["id"], to_version=2
    )
    assert rewound["position"]["version"] == 2
    assert rewound["position"]["row_offset"] == 0


def test_rewind_rejects_negative_version() -> None:
    dp_id = _seed_dp("ev", "neg")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    with pytest.raises(ValueError):
        event_port_service.rewind_subscription(
            _factory(), subscription_id=sub["id"], to_version=-1
        )


# ---------------------------------------------------------------------------
# delivery ledger
# ---------------------------------------------------------------------------


def test_record_delivery_writes_ledger_row() -> None:
    dp_id = _seed_dp("ev", "lg")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    delivery_id = event_port_service.record_delivery(
        _factory(),
        subscription_id=sub["id"],
        version_from=0,
        version_to=3,
        row_count=42,
        status="ok",
    )
    assert delivery_id > 0
    with _factory()() as session:
        row = session.scalar(
            select(DataProductEventDelivery).where(
                DataProductEventDelivery.id == delivery_id
            )
        )
    assert row is not None
    assert row.row_count == 42
    assert row.status == "ok"


def test_record_delivery_validates_status() -> None:
    dp_id = _seed_dp("ev", "stval")
    port_id = _seed_output_port(dp_id)
    sub = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="cons",
    )
    with pytest.raises(ValueError):
        event_port_service.record_delivery(
            _factory(),
            subscription_id=sub["id"],
            version_from=0,
            version_to=1,
            row_count=0,
            status="weird",
        )


# ---------------------------------------------------------------------------
# list filters
# ---------------------------------------------------------------------------


def test_list_subscriptions_filters_by_status() -> None:
    dp_id = _seed_dp("ev", "lf")
    port_id = _seed_output_port(dp_id)
    s1 = event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="active1",
    )
    event_port_service.create_subscription(
        _factory(),
        data_product_id=dp_id,
        output_port_id=port_id,
        table_name="t",
        consumer_label="active2",
    )
    event_port_service.pause_subscription(_factory(), subscription_id=s1["id"])
    paused = event_port_service.list_subscriptions(
        _factory(), data_product_id=dp_id, status="paused"
    )
    active = event_port_service.list_subscriptions(
        _factory(), data_product_id=dp_id, status="active"
    )
    assert len(paused) == 1
    assert len(active) == 1
