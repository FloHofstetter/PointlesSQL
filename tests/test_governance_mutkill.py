"""Behaviour tests targeting surviving governance mutants.

Strengthens the governance suite by asserting exact observable
outputs — persisted columns, raised-error attributes, dict keys, and
heuristic counts — that the existing tests left unchecked.  Each test
pins a behaviour that a surviving mutant would change.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductForgetRequest,
    DataProductInputPort,
    Domain,
    WorkspaceGovernancePolicy,
)
from pointlessql.services import governance as gov
from pointlessql.services.governance._consumption import (
    CONSUMPTION_BLOCKED_ACTION,
    CONSUMPTION_UNDECLARED_ACTION,
    ConsumptionDecision,
    ConsumptionVerdict,
    emit_consumption_audit,
)
from pointlessql.services.governance._forget import (
    execute_forget,
    list_forget_requests,
    propose_forget,
)
from pointlessql.services.governance._iso8601 import validate_timestamps
from pointlessql.services.governance._port_identity import (
    PortIdentityViolation,
    assert_port_identity,
)


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, tables=None) -> int:
    """Insert a minimal DataProduct row with a valid contract; return id."""
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
# right-to-be-forgotten — propose
# ---------------------------------------------------------------------------


def test_propose_forget_persists_exact_defaults() -> None:
    dp_id = _seed_dp("main", "fp_defaults")
    row = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="v-1",
        requested_by_user_id=42,
        agent_run_id="run-0007",
    )
    assert row.status == "proposed"
    assert row.tables_affected_json == "[]"
    assert row.requested_by_user_id == 42
    assert row.agent_run_id == "run-0007"
    # Reloaded row carries the same persisted shape.
    with _factory()() as session:
        stored = session.get(DataProductForgetRequest, row.id)
        assert stored is not None
        assert stored.status == "proposed"
        assert stored.tables_affected_json == "[]"
        assert stored.requested_by_user_id == 42
        assert stored.agent_run_id == "run-0007"


def test_propose_forget_requires_both_fields() -> None:
    dp_id = _seed_dp("main", "fp_required")
    # An empty column with a present value must still raise — the guard
    # is an OR, not an AND.
    with pytest.raises(ValueError, match="required"):
        propose_forget(
            _factory(),
            data_product_id=dp_id,
            subject_column="   ",
            subject_value="present",
        )
    # And the symmetric case: present column, empty value.
    with pytest.raises(ValueError, match="required"):
        propose_forget(
            _factory(),
            data_product_id=dp_id,
            subject_column="customer_id",
            subject_value="",
        )


# ---------------------------------------------------------------------------
# right-to-be-forgotten — execute
# ---------------------------------------------------------------------------


class _CountingPQL:
    """PQL stand-in returning a configurable delete-metrics dict."""

    metrics: dict[str, int] = {"num_deleted_rows": 5}
    calls: list[tuple[str, str | None]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    def delete(self, target: str, *, where: str | None = None) -> dict[str, int]:
        _CountingPQL.calls.append((target, where))
        return dict(_CountingPQL.metrics)


def _patch_pql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pointlessql.pql.PQL", _CountingPQL)
    monkeypatch.setattr("pointlessql.services.soyuz_client.make_soyuz_client", lambda _s: None)
    monkeypatch.setattr(
        "pointlessql.services.soyuz_client.make_principal_client", lambda _s, _p: None
    )


def test_execute_forget_escapes_single_quotes_in_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _seed_dp(
        "main",
        "fe_escape",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    _CountingPQL.calls = []
    _CountingPQL.metrics = {"num_deleted_rows": 5}
    _patch_pql(monkeypatch)
    execute_forget(
        _factory(),
        None,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_escape",
        subject_column="customer_id",
        subject_value="o'brien",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
    )
    # The apostrophe is doubled so the predicate is valid SQL — a mutant
    # that drops the escape would emit a single quote.
    assert _CountingPQL.calls == [("main.fe_escape.orders", "customer_id = 'o''brien'")]


def test_execute_forget_summary_keys_and_persisted_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _seed_dp(
        "main",
        "fe_actor",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    _CountingPQL.calls = []
    _CountingPQL.metrics = {"num_deleted_rows": 5}
    _patch_pql(monkeypatch)
    summary = execute_forget(
        _factory(),
        None,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_actor",
        subject_column="customer_id",
        subject_value="abc",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
        executed_by_user_id=99,
    )
    # Exact summary contract.
    assert set(summary) == {"request_id", "rows_deleted", "tables_affected", "status"}
    assert summary["rows_deleted"] == 5
    assert summary["status"] == "executed"
    assert summary["tables_affected"] == [{"table": "orders", "rows_deleted": 5}]
    # Persisted ledger row stamps the executing actor on both columns.
    with _factory()() as session:
        stored = session.get(DataProductForgetRequest, summary["request_id"])
        assert stored is not None
        assert stored.executed_by_user_id == 99
        assert stored.requested_by_user_id == 99
        assert stored.rows_deleted == 5
        assert json.loads(stored.tables_affected_json) == ["main.fe_actor.orders"]


def test_execute_forget_defaults_missing_metric_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _seed_dp(
        "main",
        "fe_zero",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    _CountingPQL.calls = []
    # The engine returns no row-count key at all.
    _CountingPQL.metrics = {}
    _patch_pql(monkeypatch)
    summary = execute_forget(
        _factory(),
        None,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_zero",
        subject_column="customer_id",
        subject_value="x",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
    )
    # A missing metric must default to 0 deletions, not 1.
    assert summary["rows_deleted"] == 0
    assert summary["tables_affected"] == [{"table": "orders", "rows_deleted": 0}]


def test_execute_forget_request_id_hash_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _seed_dp(
        "main",
        "fe_mismatch",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    proposal = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="real-subject",
    )
    _CountingPQL.calls = []
    _CountingPQL.metrics = {"num_deleted_rows": 5}
    _patch_pql(monkeypatch)
    # Executing the proposal with a DIFFERENT value must refuse — the
    # stored hash will not match.
    with pytest.raises(ValueError, match="does not match"):
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_id,
            catalog="main",
            schema="fe_mismatch",
            subject_column="customer_id",
            subject_value="wrong-subject",
            declared_tables=[("orders", ["customer_id"])],
            principal=None,
            request_id=proposal.id,
        )
    # No delete may have run.
    assert _CountingPQL.calls == []


def test_execute_forget_request_id_wrong_product_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_a = _seed_dp(
        "main",
        "fe_prod_a",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    dp_b = _seed_dp(
        "main",
        "fe_prod_b",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    proposal = propose_forget(
        _factory(),
        data_product_id=dp_a,
        subject_column="customer_id",
        subject_value="subj",
    )
    _CountingPQL.calls = []
    _CountingPQL.metrics = {"num_deleted_rows": 5}
    _patch_pql(monkeypatch)
    # Pointing product B at product A's proposal id must be rejected.
    with pytest.raises(ValueError, match="not found"):
        execute_forget(
            _factory(),
            None,
            data_product_id=dp_b,
            catalog="main",
            schema="fe_prod_b",
            subject_column="customer_id",
            subject_value="subj",
            declared_tables=[("orders", ["customer_id"])],
            principal=None,
            request_id=proposal.id,
        )
    assert _CountingPQL.calls == []


def test_execute_forget_request_id_match_updates_existing_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dp_id = _seed_dp(
        "main",
        "fe_update",
        tables=[{"name": "orders", "columns": [{"name": "customer_id", "type": "string"}]}],
    )
    proposal = propose_forget(
        _factory(),
        data_product_id=dp_id,
        subject_column="customer_id",
        subject_value="match-me",
    )
    _CountingPQL.calls = []
    _CountingPQL.metrics = {"num_deleted_rows": 5}
    _patch_pql(monkeypatch)
    summary = execute_forget(
        _factory(),
        None,
        data_product_id=dp_id,
        catalog="main",
        schema="fe_update",
        subject_column="customer_id",
        subject_value="match-me",
        declared_tables=[("orders", ["customer_id"])],
        principal=None,
        request_id=proposal.id,
    )
    # The same ledger row is updated in place, not duplicated.
    assert summary["request_id"] == proposal.id
    ledger = list_forget_requests(_factory(), data_product_id=dp_id)
    assert len(ledger) == 1
    assert ledger[0].id == proposal.id
    assert ledger[0].status == "executed"
    assert ledger[0].rows_deleted == 5


# ---------------------------------------------------------------------------
# per-output-port identity assertion
# ---------------------------------------------------------------------------


def test_port_identity_falls_back_to_aud_key() -> None:
    """A principal carrying ``aud`` (not ``oidc_aud``) is honoured."""
    req = json.dumps({"oidc_audiences": ["payments-api"]})
    # Match via the fallback key allows.
    assert_port_identity(
        requirements_json=req,
        principal={"aud": "payments-api"},
    )
    # A mismatching fallback key still raises and reports observed.
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"aud": "other-api"},
        )
    assert exc.value.constraint == "oidc_audiences"
    assert exc.value.observed == ["other-api"]


def test_port_identity_audience_list_observed_is_sorted() -> None:
    req = json.dumps({"oidc_audiences": ["payments-api"]})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"oidc_aud": ["zeta", "alpha"]},
        )
    # The observed audiences are surfaced sorted.
    assert exc.value.observed == ["alpha", "zeta"]


def test_port_identity_missing_scopes_constraint_and_observed() -> None:
    req = json.dumps({"required_scopes": ["read:data", "write:data"]})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"scopes": ["read:data"]},
        )
    assert exc.value.constraint == "required_scopes"
    # Only the missing scope is reported, sorted.
    assert exc.value.observed == ["write:data"]


def test_port_identity_space_delimited_scope_string_is_split() -> None:
    """A space-delimited scope string is parsed into individual scopes."""
    req = json.dumps({"required_scopes": ["read:data", "write:data"]})
    # The whole grant arrives as one space-joined string.
    assert_port_identity(
        requirements_json=req,
        principal={"scopes": "read:data write:data extra:scope"},
    )


def test_port_identity_min_role_reports_observed_role() -> None:
    req = json.dumps({"min_role": "steward"})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"role": "consumer"},
        )
    assert exc.value.constraint == "min_role"
    assert exc.value.observed == "consumer"


def test_port_identity_unknown_required_role_is_unreachable() -> None:
    """An unknown ``min_role`` ranks above every real role, so all fail."""
    req = json.dumps({"min_role": "superuser"})
    # Even an admin is below the unknown role's sentinel rank.
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"role": "admin"},
        )
    assert exc.value.constraint == "min_role"


def test_port_identity_unknown_observed_role_is_below_floor() -> None:
    """An unrecognised observed role ranks below the lowest real role."""
    req = json.dumps({"min_role": "viewer"})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"role": "made-up-role"},
        )
    assert exc.value.constraint == "min_role"


def test_port_identity_anonymous_blocked_when_only_scopes_required() -> None:
    """Anonymous is rejected when ANY single requirement is present."""
    req = json.dumps({"required_scopes": ["read:data"]})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(requirements_json=req, principal=None)
    assert exc.value.constraint == "authentication_required"


# ---------------------------------------------------------------------------
# ownership heuristic — full shape
# ---------------------------------------------------------------------------


def _seed_domain(slug: str, name: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        dom = Domain(
            workspace_id=1,
            slug=slug,
            name=name,
            archetype="source-aligned",
            created_at=now,
        )
        session.add(dom)
        session.commit()
        return dom.id


def _assign_domain(dp_id: int, domain_id: int) -> None:
    with _factory()() as session:
        session.get(DataProduct, dp_id).domain_id = domain_id
        session.commit()


def _add_upstream_port(agg_id: int, name: str, source_ref: str) -> None:
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=agg_id,
                name=name,
                kind="upstream_product",
                source_ref=source_ref,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


def test_suggest_domain_full_structure_and_majority_count() -> None:
    sales = _seed_domain("sales-dom", "Sales")
    up1 = _seed_dp("main", "own_up1")
    up2 = _seed_dp("main", "own_up2")
    _seed_dp("main", "own_up3")  # third upstream carries no domain
    # Two upstreams in Sales, one without a domain -> majority = Sales 2/2.
    _assign_domain(up1, sales)
    _assign_domain(up2, sales)
    agg = _seed_dp("main", "own_agg")
    _add_upstream_port(agg, "u1", "main.own_up1")
    _add_upstream_port(agg, "u2", "main.own_up2")
    _add_upstream_port(agg, "u3", "main.own_up3")

    suggestion = gov.suggest_domain_for_aggregate(_factory(), data_product_id=agg, workspace_id=1)
    assert suggestion is not None
    # Exact top-level dict keys.
    assert set(suggestion) == {"suggested_domain", "rationale", "upstream_domains"}
    sd = suggestion["suggested_domain"]
    assert sd == {"id": sales, "slug": "sales-dom", "name": "Sales"}
    # The rationale counts the two domain-bearing upstreams (not three),
    # and names the winning domain — pins most_common(1) + the counter.
    assert suggestion["rationale"] == "2 of 2 upstream products with a domain belong to 'Sales'"
    # The per-upstream list carries every declared upstream, including
    # the one with no domain.
    ud = suggestion["upstream_domains"]
    assert len(ud) == 3
    refs = {entry["ref"]: entry["domain"] for entry in ud}
    assert set(refs) == {"main.own_up1", "main.own_up2", "main.own_up3"}
    assert refs["main.own_up1"] == {"id": sales, "slug": "sales-dom", "name": "Sales"}
    assert refs["main.own_up3"] is None
    # Every upstream entry has exactly the ref/domain keys.
    for entry in ud:
        assert set(entry) == {"ref", "domain"}


def test_suggest_domain_breaks_tie_by_first_most_common() -> None:
    """With two domains tied 1-1, a single winner emerges (most_common(1))."""
    sales = _seed_domain("tie-sales", "Sales")
    eng = _seed_domain("tie-eng", "Engineering")
    up_s = _seed_dp("main", "tie_up_s")
    up_e = _seed_dp("main", "tie_up_e")
    _assign_domain(up_s, sales)
    _assign_domain(up_e, eng)
    agg = _seed_dp("main", "tie_agg")
    _add_upstream_port(agg, "us", "main.tie_up_s")
    _add_upstream_port(agg, "ue", "main.tie_up_e")
    suggestion = gov.suggest_domain_for_aggregate(_factory(), data_product_id=agg, workspace_id=1)
    assert suggestion is not None
    # Total counts both domain-bearing upstreams.
    assert suggestion["rationale"].startswith("1 of 2 upstream products")
    assert suggestion["suggested_domain"]["id"] in {sales, eng}


def test_suggest_domain_none_when_no_upstream_has_domain() -> None:
    _seed_dp("main", "nod_up")  # upstream with no domain assigned
    agg = _seed_dp("main", "nod_agg")
    _add_upstream_port(agg, "u", "main.nod_up")
    assert gov.suggest_domain_for_aggregate(_factory(), data_product_id=agg, workspace_id=1) is None


# ---------------------------------------------------------------------------
# compliance scan — audit-row provenance + result shape
# ---------------------------------------------------------------------------


def test_scan_workspace_audit_actor_defaults_and_keys() -> None:
    dp_id = _seed_dp(
        "main",
        "scan_actor",
        tables=[{"name": "orders", "columns": [{"name": "email", "type": "string"}]}],
    )
    gov.set_product_policy(_factory(), data_product_id=dp_id, fields={"retention_days": 30})
    summary = gov.scan_workspace(
        _factory(),
        None,
        workspace_id=1,
        age_provider=lambda _s, _c, _sc, _t: 100.0,
    )
    # Result envelope keys + product count.
    assert set(summary) == {"products_scanned", "violations"}
    assert summary["products_scanned"] == 1
    mine = [v for v in summary["violations"] if v.get("ref") == "main.scan_actor"]
    # Each violation carries the product id + ref keys mixed into the finding.
    for v in mine:
        assert v["data_product_id"] == dp_id
        assert v["ref"] == "main.scan_actor"
    # The audit rows use the system-actor defaults: user_id 0, the
    # "system" email + role, scoped to the workspace.
    with _factory()() as session:
        rows = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.target == "data_product:main.scan_actor",
                )
            ).all()
        )
    assert rows, "expected at least one compliance audit row"
    for row in rows:
        assert row.user_id == 0
        assert row.user_email == "system"
        assert row.actor_role == "system"
        assert row.workspace_id == 1


def test_scan_workspace_skips_retention_when_unset() -> None:
    """A product with no retention policy produces no retention findings."""
    dp_id = _seed_dp(
        "main",
        "scan_noret",
        tables=[{"name": "orders", "columns": [{"name": "email", "type": "string"}]}],
    )
    # No retention_days policy set.  The age provider would flag if called.
    summary = gov.scan_workspace(
        _factory(),
        None,
        workspace_id=1,
        age_provider=lambda _s, _c, _sc, _t: 9_999.0,
    )
    mine = [v for v in summary["violations"] if v.get("data_product_id") == dp_id]
    kinds = {v["kind"] for v in mine}
    # PII finding present, but NO retention finding (the branch is gated
    # on retention_days being set).
    assert "unclassified_pii" in kinds
    assert "retention_overdue" not in kinds


# ---------------------------------------------------------------------------
# consumption audit emission
# ---------------------------------------------------------------------------


def _decision(verdict: ConsumptionVerdict) -> ConsumptionDecision:
    return ConsumptionDecision(
        verdict=verdict,
        mode="strict" if verdict is ConsumptionVerdict.BLOCK else "advisory",
        consumer_product_id=77,
        source_fqn="cat.sch.tbl",
        declared=False,
        reason="cat.sch is not a declared input-port",
    )


def test_emit_consumption_audit_allow_is_silent() -> None:
    emit_consumption_audit(
        _factory(),
        decision=_decision(ConsumptionVerdict.ALLOW),
        user_id=1,
        user_email="u@x.com",
    )
    with _factory()() as session:
        rows = list(session.scalars(select(AuditLog)).all())
    assert rows == []


def test_emit_consumption_audit_warn_row_shape() -> None:
    emit_consumption_audit(
        _factory(),
        decision=_decision(ConsumptionVerdict.WARN),
        user_id=5,
        user_email="warner@x.com",
        client_ip="10.0.0.9",
    )
    with _factory()() as session:
        rows = list(session.scalars(select(AuditLog)).all())
    assert len(rows) == 1
    row = rows[0]
    # WARN maps to the undeclared action; defaults for actor_role/workspace.
    assert row.action == CONSUMPTION_UNDECLARED_ACTION
    assert row.target == "data_product:77"
    assert row.actor_role == "user"
    assert row.workspace_id == 1
    assert row.client_ip == "10.0.0.9"
    detail = row.detail if isinstance(row.detail, dict) else json.loads(row.detail)
    assert detail == {
        "mode": "advisory",
        "source": "cat.sch.tbl",
        "declared": False,
        "reason": "cat.sch is not a declared input-port",
    }


def test_emit_consumption_audit_block_uses_blocked_action() -> None:
    emit_consumption_audit(
        _factory(),
        decision=_decision(ConsumptionVerdict.BLOCK),
        user_id=5,
        user_email="blocker@x.com",
        actor_role="admin",
        workspace_id=3,
    )
    with _factory()() as session:
        rows = list(session.scalars(select(AuditLog)).all())
    assert len(rows) == 1
    row = rows[0]
    # BLOCK selects the blocked action constant, and the explicit
    # actor_role/workspace_id are threaded through, not defaulted.
    assert row.action == CONSUMPTION_BLOCKED_ACTION
    assert row.actor_role == "admin"
    assert row.workspace_id == 3
    detail = row.detail if isinstance(row.detail, dict) else json.loads(row.detail)
    assert detail["mode"] == "strict"


# ---------------------------------------------------------------------------
# iso8601 — finding detail + column-name heuristic tokens
# ---------------------------------------------------------------------------


def test_validate_timestamps_finding_carries_index_and_value() -> None:
    import pandas as pd

    df = pd.DataFrame({"event_time": ["2026-05-30T00:00:00Z", "nope", "2026-05-30"]})
    findings = validate_timestamps(df, mode="warn")
    assert len(findings) == 1
    f = findings[0]
    # The row index of the bad value is reported exactly (position 1).
    assert f.row_index == 1
    # The offending value is surfaced verbatim.
    assert f.value == "nope"
    assert f.column == "event_time"


@pytest.mark.parametrize(
    "column",
    ["session_ts", "event_timestamp", "birth_date", "load_dt", "shipped_time"],
)
def test_validate_timestamps_recognises_each_token(column: str) -> None:
    import pandas as pd

    # Each column name carries exactly one of the heuristic tokens; a
    # garbage value in it must be flagged.
    df = pd.DataFrame({column: ["definitely not iso"]})
    findings = validate_timestamps(df, mode="warn")
    assert [f.column for f in findings] == [column]


# ---------------------------------------------------------------------------
# policy upsert — persisted columns + workspace scoping
# ---------------------------------------------------------------------------


def test_set_workspace_policy_persists_actor_and_scopes_by_workspace() -> None:
    gov.set_workspace_policy(
        _factory(),
        workspace_id=1,
        fields={"retention_days": 90},
        updated_by_user_id=11,
    )
    with _factory()() as session:
        row = session.scalar(
            select(WorkspaceGovernancePolicy).where(WorkspaceGovernancePolicy.workspace_id == 1)
        )
        assert row is not None
        # The policy row is bound to workspace 1 and stamps its editor.
        assert row.workspace_id == 1
        assert row.retention_days == 90
        assert row.updated_by_user_id == 11


def test_set_workspace_policy_upsert_reuses_one_row() -> None:
    gov.set_workspace_policy(_factory(), workspace_id=1, fields={"retention_days": 30})
    gov.set_workspace_policy(_factory(), workspace_id=1, fields={"retention_days": 60})
    with _factory()() as session:
        rows = list(
            session.scalars(
                select(WorkspaceGovernancePolicy).where(WorkspaceGovernancePolicy.workspace_id == 1)
            ).all()
        )
    # The second write updates the same row, not a new one.
    assert len(rows) == 1
    assert rows[0].retention_days == 60


# ---------------------------------------------------------------------------
# classification delete — false on a miss
# ---------------------------------------------------------------------------


def test_delete_classification_returns_false_on_missing() -> None:
    dp_id = _seed_dp("main", "del_miss")
    # No classification with this id exists.
    assert (
        gov.delete_classification(_factory(), data_product_id=dp_id, classification_id=99999)
        is False
    )
