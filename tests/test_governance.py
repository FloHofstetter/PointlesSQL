"""Computational governance — policy, classification, masking, forget, scan.

Covers the data-mesh γ layer: per-product policy-as-code with workspace
inheritance, column classification + the read-time masking sidecar, the
right-to-be-forgotten control-port op, the compliance scanner, the
aggregate-ownership heuristic, and the control-port + admin API gates.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductInputPort,
    Domain,
    User,
)
from pointlessql.services import governance as gov
from pointlessql.services.governance._compliance import (
    COMPLIANCE_VIOLATION_ACTION,
    retention_findings,
    unclassified_pii_findings,
)
from pointlessql.services.governance._forget import (
    execute_forget,
    list_forget_requests,
    propose_forget,
)


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "test@test.com"))


def _seed_dp(catalog: str, schema: str, *, steward_user_id: int | None = None, tables=None) -> int:
    """Insert a minimal DataProduct row with a valid contract; return its id."""
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": tables or [],
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


# ---------------------------------------------------------------------------
# service — policy inheritance (E1 / E8)
# ---------------------------------------------------------------------------


def test_effective_policy_layers_product_over_workspace_over_unset() -> None:
    dp_id = _seed_dp("main", "pol_inherit")
    # workspace default sets retention; product overrides encryption only.
    gov.set_workspace_policy(_factory(), workspace_id=1, fields={"retention_days": 90})
    gov.set_product_policy(
        _factory(), data_product_id=dp_id, fields={"encryption_class": "at_rest"}
    )
    eff = gov.get_effective_policy(_factory(), data_product_id=dp_id, workspace_id=1)
    assert eff["retention_days"] == {"value": 90, "source": "workspace"}
    assert eff["encryption_class"] == {"value": "at_rest", "source": "product"}
    assert eff["residency_region"] == {"value": None, "source": "unset"}


def test_product_policy_clear_field_falls_back_to_inherit() -> None:
    dp_id = _seed_dp("main", "pol_clear")
    gov.set_workspace_policy(_factory(), workspace_id=1, fields={"retention_days": 30})
    gov.set_product_policy(_factory(), data_product_id=dp_id, fields={"retention_days": 7})
    assert (
        gov.get_effective_policy(_factory(), data_product_id=dp_id, workspace_id=1)[
            "retention_days"
        ]["value"]
        == 7
    )
    gov.set_product_policy(_factory(), data_product_id=dp_id, fields={"retention_days": None})
    eff = gov.get_effective_policy(_factory(), data_product_id=dp_id, workspace_id=1)
    assert eff["retention_days"] == {"value": 30, "source": "workspace"}


# ---------------------------------------------------------------------------
# service — classifications (E2)
# ---------------------------------------------------------------------------


def test_classification_crud_and_schema_index() -> None:
    dp_id = _seed_dp("main", "cls")
    gov.add_classification(
        _factory(),
        data_product_id=dp_id,
        catalog="main",
        schema="cls",
        table="orders",
        column="email",
        classification="pii",
    )
    index = gov.classifications_for_schema(_factory(), catalog="main", schema="cls")
    assert index[("orders", "email")] == ("pii", "partial")
    rows = gov.list_classifications(_factory(), data_product_id=dp_id)
    assert len(rows) == 1
    assert gov.delete_classification(
        _factory(), data_product_id=dp_id, classification_id=rows[0].id
    )
    assert gov.classifications_for_schema(_factory(), catalog="main", schema="cls") == {}


def test_classification_rejects_bad_class() -> None:
    dp_id = _seed_dp("main", "cls_bad")
    with pytest.raises(ValueError, match="classification"):
        gov.add_classification(
            _factory(),
            data_product_id=dp_id,
            catalog="main",
            schema="cls_bad",
            table="t",
            column="c",
            classification="bogus",
        )


def test_effective_strategy_per_class() -> None:
    assert gov.effective_strategy("phi", None) == "full"
    assert gov.effective_strategy("pii", None) == "partial"
    assert gov.effective_strategy("confidential", None) == "hash"
    assert gov.effective_strategy("public", None) == "none"
    assert gov.effective_strategy("pii", "null") == "null"  # override wins


# ---------------------------------------------------------------------------
# service — masking sidecar (B6)
# ---------------------------------------------------------------------------


def test_mask_cell_strategies() -> None:
    assert gov.mask_cell("alice@example.com", "none", secret="s") == "alice@example.com"
    assert gov.mask_cell("alice@example.com", "partial", secret="s") == "***@***.***"
    assert gov.mask_cell("anything", "full", secret="s") == "<redacted>"
    assert gov.mask_cell("anything", "null", secret="s") is None
    hashed = gov.mask_cell("anything", "hash", secret="s")
    assert hashed not in (None, "anything")
    assert gov.mask_cell(None, "full", secret="s") is None  # null stays null


def test_mask_dataframe_masks_classified_clears_when_unmask() -> None:
    df = pd.DataFrame({"email": ["a@b.com", "c@d.com"], "id": [1, 2]})
    masked = gov.mask_dataframe(df, {"email": "partial"}, unmask=False, secret="s")
    assert list(masked["email"]) == ["***@***.***", "***@***.***"]
    assert list(masked["id"]) == [1, 2]
    # unmask returns the frame untouched.
    clear = gov.mask_dataframe(df, {"email": "partial"}, unmask=True, secret="s")
    assert list(clear["email"]) == ["a@b.com", "c@d.com"]


def test_mask_sql_rows_best_effort_hit_and_miss() -> None:
    columns = ["email", "total"]
    rows = [["a@b.com", 10], ["c@d.com", 20]]
    masked = gov.mask_sql_rows(columns, rows, {"email": "partial"}, unmask=False, secret="s")
    assert masked[0][0] == "***@***.***"
    assert masked[0][1] == 10
    # an aliased/derived column name no longer matches → slips through.
    aliased = gov.mask_sql_rows(
        ["masked_mail", "total"], rows, {"email": "partial"}, unmask=False, secret="s"
    )
    assert aliased[0][0] == "a@b.com"


def test_viewer_sees_clear_rule() -> None:
    assert gov.viewer_sees_clear(is_admin=True, is_steward=False)
    assert gov.viewer_sees_clear(is_admin=False, is_steward=True)
    assert not gov.viewer_sees_clear(is_admin=False, is_steward=False)


# ---------------------------------------------------------------------------
# service — right-to-be-forgotten (E7)
# ---------------------------------------------------------------------------


def test_propose_forget_stores_hash_not_raw() -> None:
    dp_id = _seed_dp("main", "forget_prop")
    row = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="secret-123",
    )
    assert row.status == "proposed"
    assert row.subject_value_hash and row.subject_value_hash != "secret-123"


class _FakePQL:
    """Stand-in for PQL whose ``delete`` records calls + returns metrics."""

    calls: list[tuple[str, str | None]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def delete(self, target: str, *, where: str | None = None) -> dict[str, int]:
        _FakePQL.calls.append((target, where))
        return {"num_deleted_rows": 3}


def test_execute_forget_deletes_and_stamps_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    dp_id = _seed_dp(
        "main",
        "forget_exec",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    _FakePQL.calls = []
    monkeypatch.setattr("pointlessql.pql.PQL", _FakePQL)
    monkeypatch.setattr("pointlessql.services.soyuz_client.make_soyuz_client", lambda _s: None)
    monkeypatch.setattr(
        "pointlessql.services.soyuz_client.make_principal_client", lambda _s, _p: None
    )
    summary = execute_forget(
        _factory(),
        None,
        data_product_id=dp_id,
        catalog="main",
        schema="forget_exec",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
    )
    assert summary["rows_deleted"] == 3
    assert summary["status"] == "executed"
    assert _FakePQL.calls == [("main.forget_exec.orders", "customer_id = 'abc'")]
    ledger = list_forget_requests(_factory(), data_product_id=dp_id)
    assert ledger[0].status == "executed"
    assert ledger[0].rows_deleted == 3


def test_execute_forget_undeclared_column_raises() -> None:
    dp_id = _seed_dp(
        "main",
        "forget_baddcol",
        tables=[{"name": "orders", "columns": [{"name": "id", "type": "long"}]}],
    )
    with pytest.raises(ValueError, match="not declared"):
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_id,
            catalog="main",
            schema="forget_baddcol",
            subject_column="ssn",
            subject_value="x",
            declared_tables=[("orders", ["id"])],
            principal=None,
        )


# ---------------------------------------------------------------------------
# service — compliance scan (E9)
# ---------------------------------------------------------------------------


def test_unclassified_pii_findings_pure() -> None:
    from pointlessql.data_products import DataProductContract

    contract = DataProductContract.model_validate(
        {
            "name": "main.x",
            "version": "1.0.0",
            "description": "",
            "catalog": "main",
            "schema_name": "x",
            "tables": [
                {
                    "name": "t",
                    "columns": [
                        {"name": "email", "type": "string"},
                        {"name": "id", "type": "long"},
                    ],
                }
            ],
        }
    )
    findings = unclassified_pii_findings(contract, {})
    assert [f["column"] for f in findings] == ["email"]
    # once classified, no finding.
    assert unclassified_pii_findings(contract, {("t", "email"): ("pii", "partial")}) == []


def test_retention_findings_pure() -> None:
    assert retention_findings(None, {"t": 100.0}) == []
    findings = retention_findings(30, {"old": 100.0, "fresh": 5.0, "unknown": None})
    assert [f["table"] for f in findings] == ["old"]


def test_scan_workspace_logs_violations() -> None:
    dp_id = _seed_dp(
        "main",
        "scan_dp",
        tables=[{"name": "orders", "columns": [{"name": "email", "type": "string"}]}],
    )
    gov.set_product_policy(_factory(), data_product_id=dp_id, fields={"retention_days": 30})
    summary = gov.scan_workspace(
        _factory(),
        None,
        workspace_id=1,
        age_provider=lambda _s, _c, _sc, _t: 100.0,
    )
    mine = [v for v in summary["violations"] if v.get("ref") == "main.scan_dp"]
    kinds = {v["kind"] for v in mine}
    assert kinds == {"unclassified_pii", "retention_overdue"}
    # findings were written to the audit log.
    with _factory()() as session:
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.action == COMPLIANCE_VIOLATION_ACTION,
                AuditLog.target == "data_product:main.scan_dp",
            )
        ).all()
    assert len(rows) >= 2


# ---------------------------------------------------------------------------
# service — A4 ownership heuristic
# ---------------------------------------------------------------------------


def test_suggest_domain_for_aggregate_majority() -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        dom = Domain(
            workspace_id=1,
            slug="sales-own",
            name="Sales",
            archetype="source-aligned",
            created_at=now,
        )
        session.add(dom)
        session.commit()
        domain_id = dom.id
    up1 = _seed_dp("main", "agg_up1")
    _seed_dp("main", "agg_up2")
    # assign up1 to the domain.
    with _factory()() as session:
        session.get(DataProduct, up1).domain_id = domain_id
        session.commit()
    agg_id = _seed_dp("main", "agg_root")
    with _factory()() as session:
        session.add_all(
            [
                DataProductInputPort(
                    data_product_id=agg_id,
                    name="u1",
                    kind="upstream_product",
                    source_ref="main.agg_up1",
                    created_at=now,
                ),
                DataProductInputPort(
                    data_product_id=agg_id,
                    name="u2",
                    kind="upstream_product",
                    source_ref="main.agg_up2",
                    created_at=now,
                ),
            ]
        )
        session.commit()
    suggestion = gov.suggest_domain_for_aggregate(
        _factory(), data_product_id=agg_id, workspace_id=1
    )
    assert suggestion is not None
    assert suggestion["suggested_domain"]["slug"] == "sales-own"


def test_suggest_domain_none_without_upstreams() -> None:
    dp_id = _seed_dp("main", "agg_none")
    assert (
        gov.suggest_domain_for_aggregate(_factory(), data_product_id=dp_id, workspace_id=1) is None
    )


# ---------------------------------------------------------------------------
# API — control-port + discovery + admin gates
# ---------------------------------------------------------------------------


async def test_governance_aggregate_shape() -> None:
    _seed_dp("main", "gov_agg")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/main/gov_agg/governance")
    assert res.status_code == 200, res.text
    body = res.json()
    assert {
        "effective_policy",
        "classifications",
        "violations",
        "trust_downgraded",
        "forget_requests",
        "ownership_suggestion",
        "can_manage",
    } <= set(body)


async def test_policy_mutation_requires_steward_or_admin() -> None:
    _seed_dp("main", "gov_gate")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.put(
            "/api/data-products/main/gov_gate/policy", json={"retention_days": 10}
        )
    assert res.status_code in (401, 403)


async def test_classification_and_policy_via_api_as_admin() -> None:
    _seed_dp("main", "gov_admin")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.put(
            "/api/data-products/main/gov_admin/policy", json={"retention_days": 45}
        )
        assert res.status_code == 200, res.text
        assert res.json()["effective"]["retention_days"]["value"] == 45
        res = await client.post(
            "/api/data-products/main/gov_admin/classifications",
            json={"table": "orders", "column": "email", "classification": "pii"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["masking_strategy"] == "partial"


async def test_forget_op_requires_steward_or_admin() -> None:
    _seed_dp("main", "gov_forget_gate")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/main/gov_forget_gate/control/forget",
            json={"subject_column": "id", "subject_value": "1"},
        )
    assert res.status_code in (401, 403)


async def test_discovery_envelope_carries_policies_block() -> None:
    dp_id = _seed_dp(
        "main",
        "gov_disco",
        tables=[{"name": "t", "columns": [{"name": "email", "type": "string"}]}],
    )
    gov.set_product_policy(_factory(), data_product_id=dp_id, fields={"retention_days": 14})
    gov.add_classification(
        _factory(),
        data_product_id=dp_id,
        catalog="main",
        schema="gov_disco",
        table="t",
        column="email",
        classification="pii",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/main/gov_disco/discovery")
    assert res.status_code == 200, res.text
    policies = res.json()["policies"]
    assert policies["retention_days"] == 14
    assert policies["classifications"][0]["column"] == "email"
    assert policies["classifications"][0]["masking_strategy"] == "partial"


async def test_admin_governance_policy_gate_and_set() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.put("/api/admin/governance/policy", json={"retention_days": 60})
    assert res.status_code in (401, 403)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.put("/api/admin/governance/policy", json={"retention_days": 60})
        assert res.status_code == 200, res.text
        assert res.json()["workspace_default"]["retention_days"] == 60
