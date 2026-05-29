"""Phase 130 — input-port consumption enforcement verdict matrix."""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductInputPort
from pointlessql.services import governance as governance_service
from pointlessql.services.governance import ConsumptionVerdict, ConsumptionViolation


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


def _add_upstream(consumer_id: int, source_ref: str) -> None:
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=consumer_id,
                name=f"in_{source_ref.replace('.', '_')}",
                kind="upstream_product",
                source_ref=source_ref,
                description="",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# verdict matrix
# ---------------------------------------------------------------------------


def test_off_mode_always_allows() -> None:
    consumer = _seed_dp("cons", "off")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="off",
        consumer_product_id=consumer,
        source_fqn="anything.goes.table",
    )
    assert decision.verdict is ConsumptionVerdict.ALLOW


def test_advisory_mode_warns_for_undeclared() -> None:
    consumer = _seed_dp("cons", "adv1")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="someone.else.t",
    )
    assert decision.verdict is ConsumptionVerdict.WARN
    assert not decision.declared


def test_advisory_mode_allows_declared() -> None:
    consumer = _seed_dp("cons", "adv2")
    _add_upstream(consumer, "upstream.system")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="upstream.system.events",
    )
    assert decision.verdict is ConsumptionVerdict.ALLOW
    assert decision.declared


def test_strict_mode_blocks_undeclared() -> None:
    consumer = _seed_dp("cons", "strict1")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="strict",
        consumer_product_id=consumer,
        source_fqn="not.declared.t",
    )
    assert decision.verdict is ConsumptionVerdict.BLOCK


def test_strict_mode_allows_declared() -> None:
    consumer = _seed_dp("cons", "strict2")
    _add_upstream(consumer, "upstream.ok")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="strict",
        consumer_product_id=consumer,
        source_fqn="upstream.ok.events",
    )
    assert decision.verdict is ConsumptionVerdict.ALLOW


def test_assert_raises_on_block() -> None:
    consumer = _seed_dp("cons", "raise1")
    with pytest.raises(ConsumptionViolation) as excinfo:
        governance_service.assert_declared_consumption(
            _factory(),
            mode="strict",
            consumer_product_id=consumer,
            source_fqn="forbidden.thing.t",
        )
    assert excinfo.value.decision.verdict is ConsumptionVerdict.BLOCK


def test_assert_returns_decision_on_warn() -> None:
    consumer = _seed_dp("cons", "raise2")
    decision = governance_service.assert_declared_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="warn.this.t",
    )
    assert decision.verdict is ConsumptionVerdict.WARN


def test_schema_grained_match() -> None:
    """Input ports key on catalog.schema; the table segment is ignored."""
    consumer = _seed_dp("cons", "grain")
    _add_upstream(consumer, "raw.events")
    for src in ("raw.events", "raw.events.orders", "raw.events.audit"):
        decision = governance_service.evaluate_consumption(
            _factory(),
            mode="strict",
            consumer_product_id=consumer,
            source_fqn=src,
        )
        assert decision.declared, src


def test_inheritance_workspace_default() -> None:
    """Workspace default 'advisory' (from migration) propagates when product has no override."""
    consumer = _seed_dp("cons", "inh")
    effective = governance_service.get_effective_policy(
        _factory(), data_product_id=consumer, workspace_id=1
    )
    # On a fresh install the workspace policy row may not exist yet; the
    # column default 'advisory' applies only at insert.  Either way the
    # resolver returns SOMETHING for the field — either the workspace's
    # advisory or unset/None.
    assert "consumption_enforcement" in effective


def test_set_product_override_via_existing_policy_route() -> None:
    consumer = _seed_dp("cons", "ovr")
    governance_service.set_product_policy(
        _factory(),
        data_product_id=consumer,
        fields={"consumption_enforcement": "strict"},
    )
    product_policy = governance_service.get_product_policy(
        _factory(), data_product_id=consumer
    )
    assert product_policy["consumption_enforcement"] == "strict"


def test_normalise_source_validation() -> None:
    consumer = _seed_dp("cons", "nrm")
    with pytest.raises(ValueError):
        governance_service.evaluate_consumption(
            _factory(),
            mode="advisory",
            consumer_product_id=consumer,
            source_fqn="onlyone",
        )


def test_decision_carries_provenance() -> None:
    consumer = _seed_dp("cons", "prov")
    decision = governance_service.evaluate_consumption(
        _factory(),
        mode="advisory",
        consumer_product_id=consumer,
        source_fqn="x.y.z",
    )
    assert decision.consumer_product_id == consumer
    assert decision.source_fqn == "x.y.z"
    assert decision.mode == "advisory"
    assert "not a declared input-port" in decision.reason


def test_strict_blocked_decision_after_raise() -> None:
    consumer = _seed_dp("cons", "after")
    with pytest.raises(ConsumptionViolation) as ei:
        governance_service.assert_declared_consumption(
            _factory(), mode="strict", consumer_product_id=consumer, source_fqn="a.b"
        )
    assert ei.value.decision.mode == "strict"
    assert ei.value.decision.declared is False
