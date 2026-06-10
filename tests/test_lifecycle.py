"""Phase 129 — product lifecycle state machine + route + discovery surface."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AuditLog, DataProduct, User
from pointlessql.services import lifecycle as lifecycle_service
from pointlessql.services.lifecycle import LifecycleTransitionError


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "test@test.com"))


def _non_admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "nonadmin@test.com"))


def _seed_dp(catalog: str, schema: str, *, steward_user_id: int | None = None) -> int:
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
            steward_user_id=steward_user_id,
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


def _current_state(dp_id: int) -> str:
    with _factory()() as session:
        product = session.get(DataProduct, dp_id)
        return product.lifecycle_state


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------


def test_default_state_is_active() -> None:
    dp_id = _seed_dp("lc1", "ws1")
    assert _current_state(dp_id) == "active"


def test_allowed_transitions_table() -> None:
    assert lifecycle_service.allowed_targets("draft") == frozenset({"active", "archived"})
    assert lifecycle_service.allowed_targets("active") == frozenset({"deprecated", "archived"})
    assert lifecycle_service.allowed_targets("deprecated") == frozenset({"retired", "active"})
    assert lifecycle_service.allowed_targets("retired") == frozenset({"archived"})
    assert lifecycle_service.allowed_targets("archived") == frozenset({"active"})


def test_transition_drives_state_and_stamps_actor() -> None:
    dp_id = _seed_dp("lc2", "ws2")
    actor = _admin_user_id()
    updated = lifecycle_service.transition(
        _factory(),
        data_product_id=dp_id,
        target="deprecated",
        actor_user_id=actor,
    )
    assert updated.lifecycle_state == "deprecated"
    assert updated.lifecycle_changed_by_user_id == actor
    assert updated.lifecycle_changed_at is not None


def test_transition_rejects_invalid_target() -> None:
    dp_id = _seed_dp("lc3", "ws3")
    with pytest.raises(LifecycleTransitionError):
        lifecycle_service.transition(
            _factory(), data_product_id=dp_id, target="retired", actor_user_id=None
        )


def test_transition_rejects_same_state() -> None:
    dp_id = _seed_dp("lc4", "ws4")
    with pytest.raises(LifecycleTransitionError):
        lifecycle_service.transition(
            _factory(), data_product_id=dp_id, target="active", actor_user_id=None
        )


def test_retire_with_replacement_sets_successor_id() -> None:
    pred_id = _seed_dp("lc5", "ws5")
    succ_id = _seed_dp("lc5", "ws5_v2")
    # active → deprecated → retired (with successor)
    lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="deprecated", actor_user_id=None
    )
    updated = lifecycle_service.transition(
        _factory(),
        data_product_id=pred_id,
        target="retired",
        actor_user_id=None,
        replacement_data_product_id=succ_id,
    )
    assert updated.replacement_data_product_id == succ_id


def test_replacement_outside_workspace_rejected() -> None:
    pred_id = _seed_dp("lc6", "ws6")
    succ_id = _seed_dp("lc6", "ws6_v2")
    with _factory()() as session:
        session.execute(
            DataProduct.__table__.update().where(DataProduct.id == succ_id).values(workspace_id=999)
        )
        session.commit()
    lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="deprecated", actor_user_id=None
    )
    with pytest.raises(LifecycleTransitionError):
        lifecycle_service.transition(
            _factory(),
            data_product_id=pred_id,
            target="retired",
            actor_user_id=None,
            replacement_data_product_id=succ_id,
        )


def test_replacement_id_outside_retire_rejected() -> None:
    pred_id = _seed_dp("lc7", "ws7")
    succ_id = _seed_dp("lc7", "ws7_v2")
    with pytest.raises(LifecycleTransitionError):
        lifecycle_service.transition(
            _factory(),
            data_product_id=pred_id,
            target="deprecated",
            actor_user_id=None,
            replacement_data_product_id=succ_id,
        )


def test_restore_clears_successor() -> None:
    pred_id = _seed_dp("lc8", "ws8")
    succ_id = _seed_dp("lc8", "ws8_v2")
    lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="deprecated", actor_user_id=None
    )
    lifecycle_service.transition(
        _factory(),
        data_product_id=pred_id,
        target="retired",
        actor_user_id=None,
        replacement_data_product_id=succ_id,
    )
    lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="archived", actor_user_id=None
    )
    restored = lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="active", actor_user_id=None
    )
    assert restored.lifecycle_state == "active"
    assert restored.replacement_data_product_id is None


# ---------------------------------------------------------------------------
# route layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lifecycle_returns_state_and_targets() -> None:
    _seed_dp("lcr1", "ws1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/lcr1/ws1/lifecycle")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "active"
    assert sorted(body["reachable_targets"]) == ["archived", "deprecated"]


@pytest.mark.asyncio
async def test_route_transition_steward_or_admin() -> None:
    _seed_dp("lcr2", "ws2")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/lcr2/ws2/lifecycle/deprecate",
            json={"note": "EOL announced"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "deprecated"


@pytest.mark.asyncio
async def test_route_invalid_transition_returns_400() -> None:
    _seed_dp("lcr3", "ws3")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/lcr3/ws3/lifecycle/retire",
            json={},
        )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_route_propose_records_audit_only() -> None:
    dp_id = _seed_dp("lcr4", "ws4")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/lcr4/ws4/lifecycle/propose",
            json={"target": "deprecated", "note": "agent suggestion"},
        )
    assert res.status_code == 200, res.text
    assert _current_state(dp_id) == "active"  # not applied
    with _factory()() as session:
        rows = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.action == lifecycle_service.LIFECYCLE_PROPOSED_ACTION,
                    AuditLog.target == "data_product:lcr4.ws4",
                )
            ).all()
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_route_non_steward_cannot_transition() -> None:
    _seed_dp("lcr5", "ws5")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/lcr5/ws5/lifecycle/deprecate",
            json={},
        )
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_route_retire_with_replacement_uri() -> None:
    pred_id = _seed_dp("lcr6", "v1")
    _seed_dp("lcr6", "v2")
    lifecycle_service.transition(
        _factory(), data_product_id=pred_id, target="deprecated", actor_user_id=None
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        # Look up the workspace slug via the discovery endpoint of v2.
        disc = await client.get("/api/data-products/lcr6/v2/discovery")
        successor_uri = disc.json()["uri"]
        res = await client.post(
            "/api/data-products/lcr6/v1/lifecycle/retire",
            json={"replacement_uri": successor_uri, "note": "succeeded by v2"},
        )
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "retired"
    assert res.json()["replacement_uri"] == successor_uri


@pytest.mark.asyncio
async def test_discovery_envelope_carries_lifecycle_block() -> None:
    _seed_dp("lcr7", "ws7")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/lcr7/ws7/discovery")
    body = res.json()
    assert "lifecycle" in body
    assert body["lifecycle"]["state"] == "active"
    assert body["lifecycle"]["replacement_uri"] is None
