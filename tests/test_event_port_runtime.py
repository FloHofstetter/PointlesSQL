"""Event-port runtime: CDF reader + WS hub + pump + endpoints (Phase 134.3)."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductEventDelivery,
    DataProductEventSubscription,
    DataProductOutputPort,
)
from pointlessql.services import event_port as event_port_service
from pointlessql.services.event_port import _ws_hub
from pointlessql.services.event_port._cdf_reader import ChangeRow
from pointlessql.services.event_port._pump import pump_all_active, pump_subscription


def _factory():
    return app.state.session_factory


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


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


def _seed_event_port(data_product_id: int, name: str = "events_v1") -> int:
    with _factory()() as session:
        port = DataProductOutputPort(
            data_product_id=data_product_id,
            name=name,
            kind="event",
            location=None,
            format="ndjson",
            description="",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(port)
        session.commit()
        return int(port.id)


class _StubWS:
    """Minimal asyncio WebSocket stand-in capturing every send_text call."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send_text(self, payload: str) -> None:
        if self.fail:
            raise RuntimeError("send failed")
        self.sent.append(payload)


# ---------------------------------------------------------------------------
# WS hub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_lazy_create_and_release() -> None:
    hub = await _ws_hub.get_or_create_hub("test.cat.sch", "tab")
    assert hub.subscribers == []
    # idempotent
    again = await _ws_hub.get_or_create_hub("test.cat.sch", "tab")
    assert again is hub
    await _ws_hub.release_hub_if_empty("test.cat.sch", "tab")
    assert ("test.cat.sch", "tab") not in _ws_hub.hub_keys()


@pytest.mark.asyncio
async def test_hub_broadcast_delivers_to_each_subscriber() -> None:
    hub = await _ws_hub.get_or_create_hub("a.b", "t1")
    ws1 = _StubWS()
    ws2 = _StubWS()
    await _ws_hub.register(hub, ws1)
    await _ws_hub.register(hub, ws2)
    n = await _ws_hub.broadcast(hub, {"v": 1})
    assert n == 2
    assert ws1.sent == ws2.sent == ['{"v": 1}']
    await _ws_hub.deregister(hub, ws1)
    await _ws_hub.deregister(hub, ws2)
    await _ws_hub.release_hub_if_empty("a.b", "t1")


@pytest.mark.asyncio
async def test_hub_broadcast_drops_failing_subscriber() -> None:
    hub = await _ws_hub.get_or_create_hub("c.d", "t2")
    good = _StubWS()
    bad = _StubWS(fail=True)
    await _ws_hub.register(hub, good)
    await _ws_hub.register(hub, bad)
    n = await _ws_hub.broadcast(hub, {"v": 1})
    assert n == 1
    # bad is removed automatically
    assert _ws_hub.subscriber_count("c.d", "t2") == 1
    await _ws_hub.deregister(hub, good)
    await _ws_hub.release_hub_if_empty("c.d", "t2")


@pytest.mark.asyncio
async def test_hub_release_skipped_when_subscribers_remain() -> None:
    hub = await _ws_hub.get_or_create_hub("e.f", "t3")
    ws = _StubWS()
    await _ws_hub.register(hub, ws)
    await _ws_hub.release_hub_if_empty("e.f", "t3")
    assert ("e.f", "t3") in _ws_hub.hub_keys()
    await _ws_hub.deregister(hub, ws)
    await _ws_hub.release_hub_if_empty("e.f", "t3")


@pytest.mark.asyncio
async def test_subscriber_count_zero_for_unknown_hub() -> None:
    assert _ws_hub.subscriber_count("ghost.product", "any_table") == 0


# ---------------------------------------------------------------------------
# Pump (with stub reader)
# ---------------------------------------------------------------------------


def _create_sub(catalog: str, schema: str, table: str, label: str) -> tuple[int, int]:
    pid = _seed_dp(catalog, schema)
    port_id = _seed_event_port(pid)
    row = event_port_service.create_subscription(
        _factory(),
        data_product_id=pid,
        output_port_id=port_id,
        table_name=table,
        consumer_label=label,
        owner_user_id=1,
    )
    return pid, row["id"]


@pytest.mark.asyncio
async def test_pump_empty_records_empty_delivery() -> None:
    _, sid = _create_sub("evt", "empty", "orders", "stub-empty")

    def _reader(_location: str, _since: int, _max: int) -> list[ChangeRow]:
        return []

    result = await pump_subscription(
        _factory(), subscription_id=sid, max_versions=10, reader=_reader
    )
    assert result == {"status": "empty", "version_from": 0, "version_to": 0, "row_count": 0}
    # one delivery row written
    with _factory()() as session:
        rows = list(
            session.scalars(
                select(DataProductEventDelivery).where(
                    DataProductEventDelivery.subscription_id == sid
                )
            ).all()
        )
    assert len(rows) == 1
    assert rows[0].status == "empty"


@pytest.mark.asyncio
async def test_pump_with_rows_advances_position_and_records_ok() -> None:
    pid, sid = _create_sub("evt", "ok", "orders", "stub-ok")

    rows_to_yield = [
        ChangeRow(version=1, commit_timestamp="2026-05-29T00:00:00Z",
                  change_type="insert", data={"id": 1, "qty": 10}),
        ChangeRow(version=2, commit_timestamp="2026-05-29T01:00:00Z",
                  change_type="insert", data={"id": 2, "qty": 20}),
    ]

    def _reader(_location: str, _since: int, _max: int) -> list[ChangeRow]:
        return rows_to_yield

    result = await pump_subscription(
        _factory(), subscription_id=sid, max_versions=10, reader=_reader
    )
    assert result["status"] == "ok"
    assert result["row_count"] == 2
    assert result["version_to"] == 3  # last version + 1

    # cursor advanced
    with _factory()() as session:
        sub = session.get(DataProductEventSubscription, sid)
        assert sub is not None
        marker = json.loads(sub.position_marker_json or "{}")
        assert marker["version"] == 3
        delivery = list(
            session.scalars(
                select(DataProductEventDelivery).where(
                    DataProductEventDelivery.subscription_id == sid
                )
            ).all()
        )
        assert len(delivery) == 1
        assert delivery[0].status == "ok"
        assert delivery[0].row_count == 2

    # hub should have a snapshot for this product+table even if no subscribers
    assert ("evt.ok", "orders") in _ws_hub.hub_keys()
    await _ws_hub.release_hub_if_empty("evt.ok", "orders")


@pytest.mark.asyncio
async def test_pump_skips_paused_subscription() -> None:
    _, sid = _create_sub("evt", "pause", "t", "stub-paused")
    event_port_service.pause_subscription(_factory(), subscription_id=sid)
    result = await pump_subscription(
        _factory(), subscription_id=sid, max_versions=10, reader=lambda *_a: []
    )
    assert result["status"] == "skipped"
    assert "status" in result.get("reason", "")


@pytest.mark.asyncio
async def test_pump_missing_subscription_returns_skipped() -> None:
    result = await pump_subscription(
        _factory(), subscription_id=999_999, max_versions=10, reader=lambda *_a: []
    )
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_pump_broadcasts_to_live_subscribers() -> None:
    pid, sid = _create_sub("evt", "fan", "tab", "stub-fan")
    hub = await _ws_hub.get_or_create_hub("evt.fan", "tab")
    ws = _StubWS()
    await _ws_hub.register(hub, ws)
    try:
        change = ChangeRow(version=5, commit_timestamp=None,
                           change_type="insert", data={"x": 42})

        def _reader(_l: str, _s: int, _m: int) -> list[ChangeRow]:
            return [change]

        await pump_subscription(
            _factory(), subscription_id=sid, max_versions=10, reader=_reader
        )
        assert len(ws.sent) == 1
        frame = json.loads(ws.sent[0])
        assert frame["version"] == 5
        assert frame["data"] == {"x": 42}
    finally:
        await _ws_hub.deregister(hub, ws)
        await _ws_hub.release_hub_if_empty("evt.fan", "tab")


@pytest.mark.asyncio
async def test_pump_all_active_aggregates() -> None:
    _, sid1 = _create_sub("evt", "all1", "t1", "agg-1")
    _, sid2 = _create_sub("evt", "all2", "t2", "agg-2")
    event_port_service.pause_subscription(_factory(), subscription_id=sid2)

    def _reader(_l: str, _s: int, _m: int) -> list[ChangeRow]:
        return [
            ChangeRow(version=10, commit_timestamp=None, change_type="insert", data={})
        ]

    summary = await pump_all_active(_factory(), max_versions=5, reader=_reader)
    # sid1 active; sid2 paused (not active so won't be picked up)
    assert summary["pumped"] >= 1
    assert summary["ok"] >= 1


# ---------------------------------------------------------------------------
# CDF reader argument validation
# ---------------------------------------------------------------------------


def test_cdf_reader_rejects_negative_version() -> None:
    from pointlessql.services.event_port._cdf_reader import read_changes

    with pytest.raises(ValueError):
        read_changes("/nonexistent", since_version=-1, max_versions=10)


def test_cdf_reader_rejects_zero_max() -> None:
    from pointlessql.services.event_port._cdf_reader import read_changes

    with pytest.raises(ValueError):
        read_changes("/nonexistent", since_version=0, max_versions=0)


def test_cdf_reader_missing_table_returns_empty() -> None:
    from pointlessql.services.event_port._cdf_reader import read_changes

    rows = read_changes("/nonexistent/path", since_version=0, max_versions=10)
    assert rows == []


# ---------------------------------------------------------------------------
# Subscription CRUD HTTP smoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_event_subscriptions_admin_sees_all(admin_client: Any) -> None:
    pid, sid = _create_sub("evt", "httpadmin", "tab", "http-admin")
    response = await admin_client.get(
        "/api/data-products/evt/httpadmin/event-subscriptions"
    )
    assert response.status_code == 200
    items = response.json()["items"]
    ids = [i["id"] for i in items]
    assert sid in ids


@pytest.mark.asyncio
async def test_anonymous_subscriptions_list_rejected(
    anonymous_client: Any,
) -> None:
    _create_sub("evt", "httpanon", "tab", "http-anon")
    response = await anonymous_client.get(
        "/api/data-products/evt/httpanon/event-subscriptions"
    )
    assert response.status_code in (401, 403)
