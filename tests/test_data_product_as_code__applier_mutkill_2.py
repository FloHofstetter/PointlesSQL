"""Behaviour tests pinning the data-product-as-code *applier* internals.

These exercise the private applier helpers (``_apply_input_port``,
``_apply_output_port``, ``_apply_slo``, ``_apply_policies``,
``_dispatch_op``, ``_ensure_product``, ``apply_plan``) with hand-built
:class:`Op` objects so the ``dict.get(key, default)`` fallbacks the
planner-fed path never reaches are observed directly.  Every assertion
is true on the real code and false on a mutant that nulls a kwarg,
renames a dict key, swaps an action string, flips a default, or drops a
field.
"""

from __future__ import annotations

import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductEntity,
    DataProductFixture,
    DataProductInputPort,
    DataProductOutputPort,
    DataProductPolicy,
    DataProductSLO,
    User,
)
from pointlessql.services.data_product_as_code import (
    _applier as applier,
)
from pointlessql.services.data_product_as_code import (
    apply_plan,
    parse_spec,
    plan_spec,
)
from pointlessql.services.data_product_as_code._planner import Op, Plan
from pointlessql.services.governance._policy import get_product_policy


def _factory():
    return app.state.session_factory


def _wipe() -> None:
    with _factory()() as session:
        session.query(DataProductContractTestResult).delete()
        session.query(DataProductContractTest).delete()
        session.query(DataProductFixture).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProductEntity).delete()
        session.query(DataProductSLO).delete()
        session.query(DataProductOutputPort).delete()
        session.query(DataProductInputPort).delete()
        session.query(DataProduct).delete()
        session.commit()


@pytest.fixture(autouse=True)
def _clean_state():
    _wipe()
    yield
    _wipe()


def _a_user_id() -> int:
    """Return a real, FK-valid user id (foreign_keys=ON in the test DB)."""
    with _factory()() as session:
        user = session.query(User).order_by(User.id.asc()).first()
        assert user is not None
        return int(user.id)


def _make_product(catalog, schema, *, name="P", description=None) -> int:
    """Insert the top-level product row and return its id."""
    body = {"name": name, "catalog": catalog, "schema": schema}
    if description is not None:
        body["description"] = description
    return applier._ensure_product(_factory(), spec=parse_spec(body), workspace_id=1)


def _ip(action, target, after):
    return Op(kind="input_port", action=action, target=target, before=None, after=after)


def _op_port(action, target, after):
    return Op(kind="output_port", action=action, target=target, before=None, after=after)


def _slo(action, target, after, before=None):
    return Op(kind="slo", action=action, target=target, before=before, after=after)


def _pol(target, after):
    return Op(kind="policies", action="update", target=target, before=None, after=after)


# --- _apply_input_port -----------------------------------------------------


def test_input_port_add_default_kind_is_external() -> None:
    # No "kind" in after -> the add path defaults to the valid "external".
    pid = _make_product("dpac2", "ip_add_default")
    applier._apply_input_port(_factory(), _ip("add", "src", {"name": "src"}), pid, None)
    with _factory()() as session:
        row = session.query(DataProductInputPort).one()
        assert row.name == "src"
        assert row.kind == "external"


def test_input_port_update_persists_every_field() -> None:
    # The update branch deletes + recreates carrying all after fields.
    pid = _make_product("dpac2", "ip_update_all")
    uid = _a_user_id()
    applier._apply_input_port(
        _factory(), _ip("add", "src", {"name": "src", "kind": "external"}), pid, None
    )
    applier._apply_input_port(
        _factory(),
        _ip(
            "update",
            "src",
            {
                "name": "renamed_src",
                "kind": "upstream_product",
                "source_ref": "other.cat",
                "description": "now described",
            },
        ),
        pid,
        uid,
    )
    with _factory()() as session:
        rows = session.query(DataProductInputPort).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.name == "renamed_src"
        assert row.kind == "upstream_product"
        assert row.source_ref == "other.cat"
        assert row.description == "now described"
        assert row.created_by_user_id == uid


def test_input_port_update_action_string_must_match() -> None:
    # A swapped action-set element drops the recreate branch entirely.
    pid = _make_product("dpac2", "ip_update_str")
    applier._apply_input_port(
        _factory(), _ip("add", "src", {"name": "src", "kind": "external"}), pid, None
    )
    applier._apply_input_port(
        _factory(),
        _ip("update", "src", {"name": "src", "kind": "operational_system"}),
        pid,
        None,
    )
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().kind == "operational_system"


def test_input_port_update_missing_target_uses_none_sentinel() -> None:
    # next(..., None) must resolve absent target to None, not StopIteration.
    pid = _make_product("dpac2", "ip_update_absent")
    applier._apply_input_port(
        _factory(),
        _ip("update", "ghost", {"name": "ghost", "kind": "external"}),
        pid,
        None,
    )
    with _factory()() as session:
        row = session.query(DataProductInputPort).one()
        assert row.name == "ghost"
        assert row.kind == "external"


def test_input_port_update_name_falls_back_to_target() -> None:
    # No "name" in after -> recreate uses op.target, not None/"None".
    pid = _make_product("dpac2", "ip_update_name_fb")
    applier._apply_input_port(
        _factory(),
        _ip("add", "keepme", {"name": "keepme", "kind": "external"}),
        pid,
        None,
    )
    applier._apply_input_port(_factory(), _ip("update", "keepme", {"kind": "external"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().name == "keepme"


def test_input_port_update_kind_falls_back_to_existing() -> None:
    # No "kind" in after -> recreate inherits existing.kind.
    pid = _make_product("dpac2", "ip_update_kind_fb")
    applier._apply_input_port(
        _factory(),
        _ip("add", "p", {"name": "p", "kind": "upstream_product"}),
        pid,
        None,
    )
    applier._apply_input_port(_factory(), _ip("update", "p", {"name": "p"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().kind == "upstream_product"


def test_input_port_update_kind_falls_back_to_external_when_absent() -> None:
    # No existing row + no after "kind" -> the literal "external".
    pid = _make_product("dpac2", "ip_update_kind_lit")
    applier._apply_input_port(_factory(), _ip("update", "fresh", {"name": "fresh"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().kind == "external"


def test_input_port_update_after_none_coalesces_to_empty_dict() -> None:
    # `op.after or {}` must keep a present dict; `and {}` would blank it.
    pid = _make_product("dpac2", "ip_after_or")
    applier._apply_input_port(
        _factory(),
        _ip("update", "tgt", {"name": "explicit_name", "kind": "external"}),
        pid,
        None,
    )
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().name == "explicit_name"


# --- _apply_output_port ----------------------------------------------------


def test_output_port_add_records_user_id() -> None:
    pid = _make_product("dpac2", "op_add_user")
    uid = _a_user_id()
    applier._apply_output_port(
        _factory(), _op_port("add", "o", {"name": "o", "kind": "sql"}), pid, uid
    )
    with _factory()() as session:
        assert session.query(DataProductOutputPort).one().created_by_user_id == uid


def test_output_port_add_name_default_is_empty_and_rejected() -> None:
    # Default name "" fails _clean_name (raise); a None/"XXXX" mutant
    # is a non-empty accepted name, silently creating a row.
    pid = _make_product("dpac2", "op_add_noname")
    with pytest.raises(ValueError):
        applier._apply_output_port(_factory(), _op_port("add", "o", {"kind": "sql"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductOutputPort).count() == 0


def test_output_port_remove_missing_target_uses_none_sentinel() -> None:
    # Remove of an absent port is a no-op, not StopIteration.
    pid = _make_product("dpac2", "op_remove_absent")
    applier._apply_output_port(
        _factory(),
        Op(kind="output_port", action="remove", target="ghost", before=None, after=None),
        pid,
        None,
    )
    with _factory()() as session:
        assert session.query(DataProductOutputPort).count() == 0


def test_output_port_update_persists_name_kind_and_user() -> None:
    pid = _make_product("dpac2", "op_update_all")
    uid = _a_user_id()
    applier._apply_output_port(
        _factory(), _op_port("add", "o", {"name": "o", "kind": "sql"}), pid, None
    )
    applier._apply_output_port(
        _factory(),
        _op_port("update", "o", {"name": "o_renamed", "kind": "file"}),
        pid,
        uid,
    )
    with _factory()() as session:
        rows = session.query(DataProductOutputPort).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.name == "o_renamed"
        assert row.kind == "file"
        assert row.created_by_user_id == uid


def test_output_port_update_name_falls_back_to_target() -> None:
    pid = _make_product("dpac2", "op_update_name_fb")
    applier._apply_output_port(
        _factory(), _op_port("add", "keep", {"name": "keep", "kind": "sql"}), pid, None
    )
    applier._apply_output_port(_factory(), _op_port("update", "keep", {"kind": "file"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductOutputPort).one().name == "keep"


def test_output_port_update_kind_falls_back_to_existing() -> None:
    pid = _make_product("dpac2", "op_update_kind_fb")
    applier._apply_output_port(
        _factory(), _op_port("add", "o", {"name": "o", "kind": "event"}), pid, None
    )
    applier._apply_output_port(_factory(), _op_port("update", "o", {"name": "o"}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductOutputPort).one().kind == "event"


def test_output_port_update_kind_falls_back_to_sql_when_absent() -> None:
    # No existing row + no "kind" -> the literal "sql" (valid).
    pid = _make_product("dpac2", "op_update_kind_lit")
    applier._apply_output_port(
        _factory(), _op_port("update", "fresh", {"name": "fresh"}), pid, None
    )
    with _factory()() as session:
        assert session.query(DataProductOutputPort).one().kind == "sql"


# --- _apply_slo ------------------------------------------------------------


def test_slo_add_records_user_id() -> None:
    pid = _make_product("dpac2", "slo_user")
    uid = _a_user_id()
    applier._apply_slo(
        _factory(),
        _slo("add", "freshness", {"kind": "freshness", "target_value": 1.0}),
        pid,
        uid,
    )
    with _factory()() as session:
        assert session.query(DataProductSLO).one().created_by_user_id == uid


def test_slo_update_action_string_must_match() -> None:
    # A swapped {"add","update"} element drops the declare path.
    pid = _make_product("dpac2", "slo_update_str")
    applier._apply_slo(
        _factory(),
        _slo("update", "freshness", {"kind": "freshness", "target_value": 5.0}),
        pid,
        None,
    )
    with _factory()() as session:
        row = session.query(DataProductSLO).one()
        assert row.slo_kind == "freshness"
        assert row.target_value == 5.0


def test_slo_kind_read_from_after_not_target() -> None:
    # after["kind"] wins over op.target; a key/None mutant uses the
    # invalid target and would raise.
    pid = _make_product("dpac2", "slo_kind_key")
    applier._apply_slo(
        _factory(),
        _slo(
            "add",
            "not_a_real_kind",
            {"kind": "completeness", "target_value": 0.9, "comparator": "gte"},
        ),
        pid,
        None,
    )
    with _factory()() as session:
        assert session.query(DataProductSLO).one().slo_kind == "completeness"


def test_slo_kind_falls_back_to_target_when_after_lacks_kind() -> None:
    # No after["kind"] -> kind defaults to op.target (a valid kind here).
    pid = _make_product("dpac2", "slo_kind_fb")
    applier._apply_slo(_factory(), _slo("add", "volume", {"target_value": 10.0}), pid, None)
    with _factory()() as session:
        assert session.query(DataProductSLO).one().slo_kind == "volume"


def test_slo_remove_missing_target_uses_none_sentinel() -> None:
    pid = _make_product("dpac2", "slo_remove_absent")
    applier._apply_slo(
        _factory(), _slo("remove", "ghost", None, before={"kind": "ghost"}), pid, None
    )
    with _factory()() as session:
        assert session.query(DataProductSLO).count() == 0


# --- _apply_policies -------------------------------------------------------


def test_policies_drop_none_fields_keep_linked(monkeypatch) -> None:
    # Filter: keep field if `v is not None OR k == "linked_policy_module_ids"`.
    # Flipping the comparison or renaming the key changes the kept set.
    captured: dict = {}

    def _spy(session_factory, *, data_product_id, fields, updated_by_user_id=None):
        captured["fields"] = dict(fields)
        return {}

    monkeypatch.setattr(applier, "set_product_policy", _spy)
    pid = _make_product("dpac2", "pol_filter")
    applier._apply_policies(
        _factory(),
        _pol(
            "dpac2.pol_filter",
            {
                "retention_days": 30,
                "encryption_class": None,
                "linked_policy_module_ids": None,
            },
        ),
        pid,
        None,
    )
    fields = captured["fields"]
    assert "retention_days" in fields
    assert "encryption_class" not in fields
    assert "linked_policy_module_ids" in fields


def test_policies_linked_key_special_case_string_value(monkeypatch) -> None:
    # The literal key string is matched by name; a mutated string would
    # drop a None-valued linked field.
    captured: dict = {}

    def _spy(session_factory, *, data_product_id, fields, updated_by_user_id=None):
        captured["fields"] = dict(fields)
        return {}

    monkeypatch.setattr(applier, "set_product_policy", _spy)
    pid = _make_product("dpac2", "pol_linked_key")
    applier._apply_policies(
        _factory(),
        _pol("dpac2.pol_linked_key", {"linked_policy_module_ids": None}),
        pid,
        None,
    )
    assert "linked_policy_module_ids" in captured["fields"]


def test_policies_linked_json_guard_requires_membership() -> None:
    # `in fields AND isinstance(...)`; the `or` mutant indexes a missing
    # key -> KeyError.  An op without the linked key must apply cleanly.
    pid = _make_product("dpac2", "pol_guard")
    applier._apply_policies(_factory(), _pol("dpac2.pol_guard", {"retention_days": 14}), pid, None)
    assert get_product_policy(_factory(), data_product_id=pid)["retention_days"] == 14


def test_policies_linked_list_is_json_encoded() -> None:
    pid = _make_product("dpac2", "pol_encode")
    applier._apply_policies(
        _factory(),
        _pol("dpac2.pol_encode", {"linked_policy_module_ids": [3, 9]}),
        pid,
        None,
    )
    with _factory()() as session:
        assert session.query(DataProductPolicy).one().linked_policy_module_ids == "[3, 9]"


def test_policies_records_user_id() -> None:
    pid = _make_product("dpac2", "pol_user")
    uid = _a_user_id()
    applier._apply_policies(_factory(), _pol("dpac2.pol_user", {"retention_days": 7}), pid, uid)
    with _factory()() as session:
        assert session.query(DataProductPolicy).one().updated_by_user_id == uid


# --- _dispatch_op ----------------------------------------------------------


def test_dispatch_output_port_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_op")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=_op_port("add", "o", {"name": "o", "kind": "sql"}),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductOutputPort).one().created_by_user_id == uid


def test_dispatch_input_port_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_ip")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=_ip("add", "i", {"name": "i", "kind": "external"}),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductInputPort).one().created_by_user_id == uid


def test_dispatch_slo_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_slo")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=_slo("add", "freshness", {"kind": "freshness", "target_value": 1.0}),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductSLO).one().created_by_user_id == uid


def test_dispatch_entity_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_ent")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=Op(
            kind="entity",
            action="add",
            target="E",
            before=None,
            after={"name": "E", "source_table": "t", "primary_key_columns": ["a"]},
        ),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductEntity).one().created_by_user_id == uid


def test_dispatch_contract_test_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_ct")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=Op(
            kind="contract_test",
            action="add",
            target="ct",
            before=None,
            after={"name": "ct", "assertion_kind": "null_rate", "assertion_spec": {"column": "id"}},
        ),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductContractTest).one().created_by_user_id == uid


def test_dispatch_fixture_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_fx")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=Op(
            kind="fixture",
            action="add",
            target="t",
            before=None,
            after={"table_name": "t", "generator_spec": [], "row_count": 5},
        ),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductFixture).one().created_by_user_id == uid


def test_dispatch_policies_threads_user_id() -> None:
    pid = _make_product("dpac2", "disp_pol")
    uid = _a_user_id()
    applier._dispatch_op(
        _factory(),
        op=_pol("dpac2.disp_pol", {"retention_days": 3}),
        product_id=pid,
        user_id=uid,
    )
    with _factory()() as session:
        assert session.query(DataProductPolicy).one().updated_by_user_id == uid


def test_dispatch_unknown_kind_raises_with_message() -> None:
    pid = _make_product("dpac2", "disp_unknown")
    with pytest.raises(NotImplementedError) as excinfo:
        applier._dispatch_op(
            _factory(),
            op=Op(kind="mystery", action="add", target="x", before=None, after={}),
            product_id=pid,
            user_id=None,
        )
    assert "unknown op kind" in str(excinfo.value)


# --- _ensure_product -------------------------------------------------------


def _read_contract(product_id: int) -> dict:
    with _factory()() as session:
        row = session.get(DataProduct, product_id)
        assert row is not None
        return json.loads(row.contract_json)


def test_ensure_product_contract_dict_keys_and_values() -> None:
    # Exact discovery-shaped contract keys + the "1.0.0" version value.
    pid = _make_product("dpac2", "ens_keys", name="Nice", description="a desc")
    contract = _read_contract(pid)
    assert contract["name"] == "Nice"
    assert contract["version"] == "1.0.0"
    assert contract["description"] == "a desc"
    assert contract["catalog"] == "dpac2"
    assert contract["schema_name"] == "ens_keys"
    assert contract["tables"] == []


def test_ensure_product_contract_description_defaults_to_empty() -> None:
    # No description -> contract stores "" (kills `or "XXXX"`/`and ""`).
    pid = _make_product("dpac2", "ens_no_desc")
    assert _read_contract(pid)["description"] == ""


def test_ensure_product_contract_keeps_description_value() -> None:
    # A real description survives (kills `spec.description and ""`).
    pid = _make_product("dpac2", "ens_desc_kept", description="keep this")
    assert _read_contract(pid)["description"] == "keep this"


def test_ensure_product_row_scalar_fields() -> None:
    # workspace_id=1, version "1.0.0", 64-char zero hash.
    pid = _make_product("dpac2", "ens_scalars")
    with _factory()() as session:
        row = session.get(DataProduct, pid)
        assert row is not None
        assert row.workspace_id == 1
        assert row.version == "1.0.0"
        assert row.contract_yaml_hash == "0" * 64
        assert len(row.contract_yaml_hash) == 64


def test_ensure_product_update_rewrites_contract_json() -> None:
    # Second ensure hits the update branch; json.dumps(contract) keeps
    # the name recoverable (kills json.dumps(None) -> "null").
    pid1 = _make_product("dpac2", "ens_update", name="First", description="v1")
    pid2 = _make_product("dpac2", "ens_update", name="Second", description="v2")
    assert pid1 == pid2
    contract = _read_contract(pid2)
    assert isinstance(contract, dict)
    assert contract["name"] == "Second"
    assert contract["description"] == "v2"


# --- apply_plan ------------------------------------------------------------


def test_apply_plan_dry_run_counters_are_zero() -> None:
    # Dry run: total only; applied + skipped 0, errors [].
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac2",
            "schema": "dry_counters",
            "output_ports": [{"name": "o", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    outcome = apply_plan(_factory(), spec=spec, plan=plan, dry_run=True)
    assert outcome.dry_run is True
    assert outcome.total == plan.op_count()
    assert outcome.applied == 0
    assert outcome.skipped == 0
    assert outcome.errors == []


def test_apply_plan_applied_count_increments_by_one_per_op() -> None:
    # Exact applied total kills the dispatch-path `applied += 2`.
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac2",
            "schema": "applied_count",
            "output_ports": [{"name": "o1", "kind": "sql"}, {"name": "o2", "kind": "file"}],
            "input_ports": [{"name": "i1", "kind": "external"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.applied == plan.op_count()
    assert outcome.skipped == 0
    assert outcome.errors == []


def test_apply_plan_records_error_tuple_for_bad_op() -> None:
    # A duplicate-port add raises ValueError -> captured as (target, msg).
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac2",
            "schema": "err_tuple",
            "output_ports": [{"name": "dup", "kind": "sql"}],
        }
    )
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    dup_op = _op_port("add", "dup", {"name": "dup", "kind": "sql"})
    plan = Plan(additions=[dup_op], modifications=[], removals=[], product_present=True)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.applied == 0
    assert len(outcome.errors) == 1
    target, message = outcome.errors[0]
    assert target == "output_port:dup"
    assert "already exists" in message


def test_apply_plan_skips_unimplemented_op_kind() -> None:
    # NotImplementedError op bumps skipped by exactly one each.
    spec = parse_spec({"name": "P", "catalog": "dpac2", "schema": "skip_count"})
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    unknown = [
        Op(kind="mystery", action="add", target=f"x{i}", before=None, after={}) for i in range(3)
    ]
    plan = Plan(additions=unknown, modifications=[], removals=[], product_present=True)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.skipped == 3
    assert outcome.applied == 0


def test_apply_plan_outcome_total_and_skipped_reflect_plan() -> None:
    # total mirrors plan.op_count(); skipped reflects the skip count.
    spec = parse_spec({"name": "P", "catalog": "dpac2", "schema": "total_skip"})
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    unknown = [Op(kind="mystery", action="add", target="x", before=None, after={})]
    plan = Plan(additions=unknown, modifications=[], removals=[], product_present=True)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.total == plan.op_count() == 1
    assert outcome.skipped == 1


def test_apply_plan_product_branch_increments_not_resets() -> None:
    # The product op does `applied += 1`, not `applied = 1`: ordering a
    # successful op before it makes a reset observable (2 vs 1).
    spec = parse_spec({"name": "P", "catalog": "dpac2", "schema": "prod_branch"})
    ordered = [
        _op_port("add", "o", {"name": "o", "kind": "sql"}),
        Op(kind="product", action="add", target="dpac2.prod_branch", before=None, after={}),
    ]
    plan = Plan(additions=ordered, modifications=[], removals=[], product_present=False)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.applied == 2
