"""Behaviour tests targeting surviving mutants in the data-product-as-code
applier's per-kind handlers.

These exercise the private ``_apply_contract_test`` / ``_apply_entity`` /
``_apply_fixture`` / ``_apply_input_port`` helpers directly with
hand-built :class:`Op` objects so the exact dict-key reads, ``.get``
defaults, action-string comparisons, and remove-path lookups can be
pinned.  Each assertion is true on the real code and false on the
corresponding mutant: a renamed key falls through to a different value,
a flipped comparison removes the wrong row, a dropped kwarg nulls a
persisted field, and so on.
"""

from __future__ import annotations

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
    Workspace,
)
from pointlessql.services.data_product_as_code import apply_plan, plan_spec
from pointlessql.services.data_product_as_code._applier import (
    _apply_contract_test,
    _apply_entity,
    _apply_fixture,
    _apply_input_port,
    _ensure_product,
)
from pointlessql.services.data_product_as_code._planner import Op
from pointlessql.services.data_product_as_code._spec import parse_spec


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


def _seeded_user_id() -> int:
    """Return a real seeded user id (FK-safe under Postgres + SQLite)."""
    with _factory()() as session:
        user = session.query(User).first()
        assert user is not None
        return int(user.id)


def _make_product() -> int:
    """Create the owning product row and return its id."""
    spec = parse_spec({"name": "P", "catalog": "dpac", "schema": "applier_chunk1"})
    return _ensure_product(_factory(), spec=spec, workspace_id=1)


# ---------------------------------------------------------------------------
# contract_test — add path: dict keys, defaults, created_by, action string
# ---------------------------------------------------------------------------


def test_contract_test_add_reads_name_key_not_target() -> None:
    """``name`` is read from after["name"], not the op.target fallback.

    Kills the ``after.get(None, ...)`` and ``"name" -> "NAME"`` key
    mutants: those fall back to op.target instead of the real name.
    """
    pid = _make_product()
    op = Op(
        kind="contract_test",
        action="add",
        target="the_target",
        before=None,
        after={
            "name": "the_real_name",
            "assertion_kind": "null_rate",
            "assertion_spec": {"column": "id"},
            "severity": "error",
            "enabled": False,
        },
    )
    _apply_contract_test(_factory(), op, pid, _seeded_user_id())
    with _factory()() as session:
        row = session.query(DataProductContractTest).one()
        assert row.name == "the_real_name"


def test_contract_test_add_name_falls_back_to_target_when_absent() -> None:
    """When after omits ``name`` the persisted name is op.target.

    Kills the default mutant ``after.get("name", op.target)`` ->
    ``after.get("name", None)`` (str(None) == 'None').
    """
    pid = _make_product()
    op = Op(
        kind="contract_test",
        action="add",
        target="fallback_name",
        before=None,
        after={
            "assertion_kind": "null_rate",
            "assertion_spec": {"column": "id"},
        },
    )
    _apply_contract_test(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductContractTest).one()
        assert row.name == "fallback_name"


def test_contract_test_add_applies_defaults_for_omitted_fields() -> None:
    """Omitted severity/enabled/assertion_spec take their literal defaults.

    Kills the default-value mutants on assertion_spec ({} -> None,
    str 'null' vs '{}'), severity ('warn' -> None/'WARN' would raise),
    and enabled (True -> False/None).
    """
    pid = _make_product()
    op = Op(
        kind="contract_test",
        action="add",
        target="ct_defaults",
        before=None,
        after={"assertion_kind": "null_rate"},
    )
    _apply_contract_test(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductContractTest).one()
        assert row.assertion_spec_json == "{}"
        assert row.severity == "warn"
        assert bool(row.enabled) is True


def test_contract_test_add_persists_created_by_user_id() -> None:
    """created_by_user_id carries the caller's user_id, not None."""
    pid = _make_product()
    uid = _seeded_user_id()
    op = Op(
        kind="contract_test",
        action="add",
        target="ct_user",
        before=None,
        after={
            "name": "ct_user",
            "assertion_kind": "null_rate",
            "assertion_spec": {},
        },
    )
    _apply_contract_test(_factory(), op, pid, uid)
    with _factory()() as session:
        row = session.query(DataProductContractTest).one()
        assert row.created_by_user_id == uid


def test_contract_test_update_action_declares_the_test() -> None:
    """``op.action == 'update'`` must still hit the declare branch.

    Kills the set-member mutants ``"update" -> "UPDATE"`` that would
    drop the update action out of the {"add", "update"} guard.
    """
    pid = _make_product()
    op = Op(
        kind="contract_test",
        action="update",
        target="ct_upd",
        before=None,
        after={
            "name": "ct_upd",
            "assertion_kind": "null_rate",
            "assertion_spec": {},
        },
    )
    _apply_contract_test(_factory(), op, pid, None)
    with _factory()() as session:
        assert session.query(DataProductContractTest).count() == 1


# ---------------------------------------------------------------------------
# contract_test — remove path: action guard, lookup, deletion
# ---------------------------------------------------------------------------


def _add_contract_test(pid: int, name: str) -> None:
    op = Op(
        kind="contract_test",
        action="add",
        target=name,
        before=None,
        after={
            "name": name,
            "assertion_kind": "null_rate",
            "assertion_spec": {},
        },
    )
    _apply_contract_test(_factory(), op, pid, None)


def test_contract_test_remove_deletes_only_the_targeted_row() -> None:
    """Remove drops exactly the named test and leaves the other intact.

    Kills the remove-branch guard flips, the ``tests = None`` /
    ``target = None`` lookups, the ``== -> !=`` name comparison, the
    ``is not None -> is None`` deletion guard, and the int(target["id"])
    key/arg mutants — any of which either skips the delete, removes the
    wrong row, or raises.
    """
    pid = _make_product()
    _add_contract_test(pid, "keep")
    _add_contract_test(pid, "drop")
    op = Op(
        kind="contract_test",
        action="remove",
        target="drop",
        before={"name": "drop"},
        after=None,
    )
    _apply_contract_test(_factory(), op, pid, None)
    with _factory()() as session:
        names = {r.name for r in session.query(DataProductContractTest).all()}
        assert names == {"keep"}


def test_contract_test_remove_missing_target_is_noop() -> None:
    """Removing an absent test changes nothing and never raises.

    Kills the ``next(gen)`` default-drop mutant (StopIteration) and any
    lookup that would error rather than no-op when nothing matches.
    """
    pid = _make_product()
    _add_contract_test(pid, "present")
    op = Op(
        kind="contract_test",
        action="remove",
        target="ghost",
        before={"name": "ghost"},
        after=None,
    )
    _apply_contract_test(_factory(), op, pid, None)
    with _factory()() as session:
        names = {r.name for r in session.query(DataProductContractTest).all()}
        assert names == {"present"}


# ---------------------------------------------------------------------------
# entity — add path: keys, defaults, created_by, action string
# ---------------------------------------------------------------------------


def test_entity_add_reads_name_key_not_target() -> None:
    """entity_name comes from after["name"], not op.target."""
    pid = _make_product()
    op = Op(
        kind="entity",
        action="add",
        target="ent_target",
        before=None,
        after={
            "name": "ent_real",
            "source_table": "src_tbl",
            "primary_key_columns": ["id"],
            "description": "d",
        },
    )
    _apply_entity(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductEntity).one()
        assert row.entity_name == "ent_real"


def test_entity_add_name_falls_back_to_target_when_absent() -> None:
    """When after omits ``name`` the entity is named op.target."""
    pid = _make_product()
    op = Op(
        kind="entity",
        action="add",
        target="ent_fallback",
        before=None,
        after={
            "source_table": "src_tbl",
            "primary_key_columns": ["id"],
        },
    )
    _apply_entity(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductEntity).one()
        assert row.entity_name == "ent_fallback"


def test_entity_add_source_table_default_empty_raises() -> None:
    """Omitting ``source_table`` defaults to '' which declare rejects.

    Kills the default mutants ('' -> None / dropped / 'XXXX'): the
    empty-string default makes declare_entity raise; any non-empty
    mutant default would succeed instead.
    """
    pid = _make_product()
    op = Op(
        kind="entity",
        action="add",
        target="ent_no_src",
        before=None,
        after={
            "name": "ent_no_src",
            "primary_key_columns": ["id"],
        },
    )
    with pytest.raises(ValueError):
        _apply_entity(_factory(), op, pid, None)


def test_entity_add_persists_created_by_user_id() -> None:
    """created_by_user_id carries the caller's user_id, not None."""
    pid = _make_product()
    uid = _seeded_user_id()
    op = Op(
        kind="entity",
        action="add",
        target="ent_user",
        before=None,
        after={
            "name": "ent_user",
            "source_table": "src",
            "primary_key_columns": ["id"],
        },
    )
    _apply_entity(_factory(), op, pid, uid)
    with _factory()() as session:
        row = session.query(DataProductEntity).one()
        assert row.created_by_user_id == uid


def test_entity_update_action_declares_the_entity() -> None:
    """``op.action == 'update'`` must still hit the declare branch."""
    pid = _make_product()
    op = Op(
        kind="entity",
        action="update",
        target="ent_upd",
        before=None,
        after={
            "name": "ent_upd",
            "source_table": "src",
            "primary_key_columns": ["id"],
        },
    )
    _apply_entity(_factory(), op, pid, None)
    with _factory()() as session:
        assert session.query(DataProductEntity).count() == 1


# ---------------------------------------------------------------------------
# entity — remove path
# ---------------------------------------------------------------------------


def _add_entity(pid: int, name: str) -> None:
    op = Op(
        kind="entity",
        action="add",
        target=name,
        before=None,
        after={
            "name": name,
            "source_table": "src",
            "primary_key_columns": ["id"],
        },
    )
    _apply_entity(_factory(), op, pid, None)


def test_entity_remove_deletes_only_the_targeted_row() -> None:
    """Remove drops exactly the named entity, leaving the other intact."""
    pid = _make_product()
    _add_entity(pid, "keep")
    _add_entity(pid, "drop")
    op = Op(
        kind="entity",
        action="remove",
        target="drop",
        before={"name": "drop"},
        after=None,
    )
    _apply_entity(_factory(), op, pid, None)
    with _factory()() as session:
        names = {r.entity_name for r in session.query(DataProductEntity).all()}
        assert names == {"keep"}


def test_entity_remove_missing_target_is_noop() -> None:
    """Removing an absent entity changes nothing and never raises."""
    pid = _make_product()
    _add_entity(pid, "present")
    op = Op(
        kind="entity",
        action="remove",
        target="ghost",
        before={"name": "ghost"},
        after=None,
    )
    _apply_entity(_factory(), op, pid, None)
    with _factory()() as session:
        names = {r.entity_name for r in session.query(DataProductEntity).all()}
        assert names == {"present"}


# ---------------------------------------------------------------------------
# fixture — add path: keys, defaults, created_by, action string
# ---------------------------------------------------------------------------


def test_fixture_add_reads_table_name_key_not_target() -> None:
    """table_name comes from after["table_name"], not op.target."""
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_target",
        before=None,
        after={
            "table_name": "fx_real",
            "generator_spec": [{"column": "id"}],
            "row_count": 7,
        },
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert row.table_name == "fx_real"


def test_fixture_add_table_name_falls_back_to_target_when_absent() -> None:
    """When after omits ``table_name`` the fixture is named op.target."""
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_fallback",
        before=None,
        after={"generator_spec": [{"column": "id"}], "row_count": 5},
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert row.table_name == "fx_fallback"


def test_fixture_add_generator_spec_defaults_to_empty_list() -> None:
    """Omitted generator_spec defaults to [] -> json '[]', not 'null'.

    Kills the default mutant ([] -> None): json.dumps(None) == 'null'.
    """
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_gen_default",
        before=None,
        after={"table_name": "fx_gen_default", "row_count": 3},
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert row.generator_spec_json == "[]"


def test_fixture_add_row_count_default_is_100_when_absent() -> None:
    """Omitted row_count defaults to 100, not 101.

    Kills the ``after.get("row_count", 100) -> 101`` literal mutant.
    """
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_rc_default",
        before=None,
        after={
            "table_name": "fx_rc_default",
            "generator_spec": [{"column": "id"}],
        },
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert int(row.row_count) == 100


def test_fixture_add_zero_row_count_falls_back_to_100() -> None:
    """A falsy row_count of 0 falls back through ``or 100`` to 100.

    Kills the ``... or 100 -> ... or 101`` mutant: with row_count 0
    present, the fallback constant is what lands.
    """
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_zero",
        before=None,
        after={
            "table_name": "fx_zero",
            "generator_spec": [{"column": "id"}],
            "row_count": 0,
        },
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert int(row.row_count) == 100


def test_fixture_add_persists_created_by_user_id() -> None:
    """created_by_user_id carries the caller's user_id, not None."""
    pid = _make_product()
    uid = _seeded_user_id()
    op = Op(
        kind="fixture",
        action="add",
        target="fx_user",
        before=None,
        after={
            "table_name": "fx_user",
            "generator_spec": [{"column": "id"}],
            "row_count": 5,
        },
    )
    _apply_fixture(_factory(), op, pid, uid)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert row.created_by_user_id == uid


def test_fixture_update_action_declares_the_fixture() -> None:
    """``op.action == 'update'`` must still hit the declare branch."""
    pid = _make_product()
    op = Op(
        kind="fixture",
        action="update",
        target="fx_upd",
        before=None,
        after={
            "table_name": "fx_upd",
            "generator_spec": [{"column": "id"}],
            "row_count": 5,
        },
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        assert session.query(DataProductFixture).count() == 1


# ---------------------------------------------------------------------------
# fixture — remove path
# ---------------------------------------------------------------------------


def _add_fixture(pid: int, table_name: str) -> None:
    op = Op(
        kind="fixture",
        action="add",
        target=table_name,
        before=None,
        after={
            "table_name": table_name,
            "generator_spec": [{"column": "id"}],
            "row_count": 5,
        },
    )
    _apply_fixture(_factory(), op, pid, None)


def test_fixture_remove_deletes_only_the_targeted_row() -> None:
    """Remove drops exactly the named fixture, leaving the other intact."""
    pid = _make_product()
    _add_fixture(pid, "keep")
    _add_fixture(pid, "drop")
    op = Op(
        kind="fixture",
        action="remove",
        target="drop",
        before={"table_name": "drop"},
        after=None,
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        tables = {r.table_name for r in session.query(DataProductFixture).all()}
        assert tables == {"keep"}


def test_fixture_remove_missing_target_is_noop() -> None:
    """Removing an absent fixture changes nothing and never raises."""
    pid = _make_product()
    _add_fixture(pid, "present")
    op = Op(
        kind="fixture",
        action="remove",
        target="ghost",
        before={"table_name": "ghost"},
        after=None,
    )
    _apply_fixture(_factory(), op, pid, None)
    with _factory()() as session:
        tables = {r.table_name for r in session.query(DataProductFixture).all()}
        assert tables == {"present"}


# ---------------------------------------------------------------------------
# input_port — add path created_by + name default; update path source_ref +
# description reads
# ---------------------------------------------------------------------------


def test_input_port_add_persists_created_by_user_id() -> None:
    """created_by_user_id carries the caller's user_id, not None."""
    pid = _make_product()
    uid = _seeded_user_id()
    op = Op(
        kind="input_port",
        action="add",
        target="ip_user",
        before=None,
        after={"name": "ip_user", "kind": "external"},
    )
    _apply_input_port(_factory(), op, pid, uid)
    with _factory()() as session:
        row = session.query(DataProductInputPort).one()
        assert row.created_by_user_id == uid


def test_input_port_add_missing_name_default_empty_raises() -> None:
    """Omitting ``name`` defaults to '' which the port validator rejects.

    Kills the default mutants ('' -> None / dropped / 'XXXX'): the
    empty-string default makes create_input_port raise; any non-empty
    mutant default would create a port instead.
    """
    pid = _make_product()
    op = Op(
        kind="input_port",
        action="add",
        target="ip_no_name",
        before=None,
        after={"kind": "external"},
    )
    with pytest.raises(ValueError):
        _apply_input_port(_factory(), op, pid, None)


def _add_input_port(pid: int, name: str) -> None:
    op = Op(
        kind="input_port",
        action="add",
        target=name,
        before=None,
        after={
            "name": name,
            "kind": "external",
            "source_ref": "orig.ref",
            "description": "orig desc",
        },
    )
    _apply_input_port(_factory(), op, pid, None)


def test_input_port_update_carries_source_ref_and_description() -> None:
    """The update path reads source_ref/description from after by key.

    Kills the ``after.get(None)`` and renamed-key mutants on both
    source_ref and description: the re-created port must carry the new
    values, not None.
    """
    pid = _make_product()
    _add_input_port(pid, "ip_upd")
    op = Op(
        kind="input_port",
        action="update",
        target="ip_upd",
        before=None,
        after={
            "name": "ip_upd",
            "kind": "external",
            "source_ref": "new.ref",
            "description": "new desc",
        },
    )
    _apply_input_port(_factory(), op, pid, None)
    with _factory()() as session:
        row = session.query(DataProductInputPort).one()
        assert row.source_ref == "new.ref"
        assert row.description == "new desc"


# ---------------------------------------------------------------------------
# ensure_product — the passed workspace_id reaches the inserted row.  The
# DataProduct.workspace_id column carries ``server_default='1'``, so feeding
# workspace_id=1 cannot tell the real assignment apart from a NULL/omitted
# value (the server default backfills 1 either way).  Seeding a *second*
# workspace and inserting under it exposes the difference: the real code
# stores 2, while nulling or dropping the kwarg lets the server default
# write 1.
# ---------------------------------------------------------------------------


def _seed_second_workspace() -> int:
    """Create workspace id=2 (FK target for the cross-workspace insert)."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    with _factory()() as session:
        session.add(
            Workspace(
                id=2,
                slug="second",
                name="Second workspace",
                description=None,
                created_at=now,
            )
        )
        session.commit()
    return 2


def test_ensure_product_stores_the_passed_workspace_id() -> None:
    """The inserted DataProduct row carries the workspace_id argument.

    Kills the ``workspace_id=None`` and dropped-``workspace_id`` mutants:
    both let the column's ``server_default='1'`` fill in 1, whereas the
    real code stores the 2 it was handed.
    """
    ws_id = _seed_second_workspace()
    spec = parse_spec({"name": "P", "catalog": "dpac", "schema": "ws2_insert"})
    pid = _ensure_product(_factory(), spec=spec, workspace_id=ws_id)
    with _factory()() as session:
        row = session.get(DataProduct, pid)
        assert row is not None
        assert row.workspace_id == ws_id


# ---------------------------------------------------------------------------
# apply_plan — the user_id argument reaches each dispatched op's CRUD write
# as created_by_user_id (the dispatch call-site passes it straight through).
# ---------------------------------------------------------------------------


def test_apply_plan_propagates_user_id_to_created_by() -> None:
    """A real user_id lands on the written port's created_by_user_id.

    Kills the dispatch call-site ``user_id=None`` mutant: nulling the
    argument would leave every written row's created_by_user_id NULL
    instead of the caller's id.
    """
    uid = _seeded_user_id()
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "uid_dispatch",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    apply_plan(_factory(), spec=spec, plan=plan, user_id=uid)
    with _factory()() as session:
        row = session.query(DataProductOutputPort).one()
        assert row.created_by_user_id == uid
