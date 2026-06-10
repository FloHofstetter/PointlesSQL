"""Cedar policy-as-code hook integration with the PQL hook registry (Phase 141)."""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator

import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import PermissionDeniedError
from pointlessql.models import (
    DataProduct,
    DataProductPolicy,
    PolicyModule,
    PolicyModuleDecision,
)
from pointlessql.pql._hooks import (
    HookContext,
    registered_counts,
    run_before_read,
    run_before_write,
)
from pointlessql.services.policy_as_code import (
    create_module,
    link_modules_to_product,
)
from pointlessql.services.policy_as_code._bootstrap import (
    register_cedar_hooks,
    reset_for_tests,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_dp(catalog: str, schema: str) -> int:
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
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(row)
        session.commit()
        return int(row.id)


def _wipe_state() -> None:
    with _factory()() as session:
        session.query(PolicyModuleDecision).delete()
        session.query(PolicyModule).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProduct).delete()
        session.commit()


@pytest.fixture
def hook_env() -> Iterator[None]:
    """Snapshot the hook registry + Cedar bootstrap flag for each test."""
    _wipe_state()
    reset_for_tests()
    with HookContext():
        register_cedar_hooks(_factory())
        yield
    reset_for_tests()
    _wipe_state()


def test_register_cedar_hooks_is_idempotent(hook_env: None) -> None:
    counts = registered_counts()
    register_cedar_hooks(_factory())
    again = registered_counts()
    assert counts == again
    assert counts["before_read"] == 1
    assert counts["before_write"] == 1


def test_unlinked_product_passes_through_hook(hook_env: None) -> None:
    dp_id = _seed_dp("hook", "pass_through")
    run_before_read(
        {
            "full_name": "hook.pass_through.foo",
            "principal": {"id": 1, "email": "a@b.test"},
            "authoring_product_id": dp_id,
            "workspace_id": 1,
        }
    )


def test_permit_module_allows_read(hook_env: None) -> None:
    dp_id = _seed_dp("hook", "permit_read")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="permit_all_reads",
        cedar_source='permit(principal, action == Action::"read", resource);',
        created_by_user_id=None,
    )
    link_modules_to_product(
        _factory(),
        data_product_id=dp_id,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    run_before_read(
        {
            "full_name": "hook.permit_read.metrics",
            "principal": {"id": 1, "email": "a@b.test"},
            "authoring_product_id": dp_id,
            "workspace_id": 1,
        }
    )
    with _factory()() as session:
        rows = session.query(PolicyModuleDecision).all()
        assert len(rows) == 1
        assert rows[0].effect == "permit"


def test_forbid_module_raises_permission_error(hook_env: None) -> None:
    dp_id = _seed_dp("hook", "forbid_read")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="forbid_all_reads",
        cedar_source='forbid(principal, action == Action::"read", resource);',
        created_by_user_id=None,
    )
    link_modules_to_product(
        _factory(),
        data_product_id=dp_id,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    with pytest.raises(PermissionDeniedError):
        run_before_read(
            {
                "full_name": "hook.forbid_read.metrics",
                "principal": {"id": 1, "email": "a@b.test"},
                "authoring_product_id": dp_id,
                "workspace_id": 1,
            }
        )


def test_before_write_uses_write_action(hook_env: None) -> None:
    dp_id = _seed_dp("hook", "writes_only")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="permit_read_block_write",
        cedar_source=(
            'permit(principal, action == Action::"read", resource);\n'
            'forbid(principal, action == Action::"write", resource);'
        ),
        created_by_user_id=None,
    )
    link_modules_to_product(
        _factory(),
        data_product_id=dp_id,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    run_before_read(
        {
            "full_name": "hook.writes_only.foo",
            "principal": {"id": 1, "email": "a@b.test"},
            "authoring_product_id": dp_id,
            "workspace_id": 1,
        }
    )
    with pytest.raises(PermissionDeniedError):
        run_before_write(
            None,
            {
                "full_name": "hook.writes_only.foo",
                "principal": {"id": 1, "email": "a@b.test"},
                "authoring_product_id": dp_id,
                "workspace_id": 1,
            },
        )


def test_broken_policy_fails_closed(hook_env: None) -> None:
    dp_id = _seed_dp("hook", "broken_policy")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="garbage_policy",
        cedar_source="this is not cedar source",
        created_by_user_id=None,
    )
    link_modules_to_product(
        _factory(),
        data_product_id=dp_id,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    with pytest.raises(PermissionDeniedError):
        run_before_read(
            {
                "full_name": "hook.broken_policy.foo",
                "principal": {"id": 1, "email": "a@b.test"},
                "authoring_product_id": dp_id,
                "workspace_id": 1,
            }
        )
    with _factory()() as session:
        rows = session.query(PolicyModuleDecision).all()
        assert rows
        context = json.loads(rows[0].context_json or "{}")
        assert context.get("error_class") in {
            "cedar_parse_error",
            "cedar_runtime_error",
        }


def test_missing_authoring_product_id_skips_hook(hook_env: None) -> None:
    run_before_read(
        {
            "full_name": "nope.nope.nope",
            "principal": {"id": 1, "email": "a@b.test"},
            "workspace_id": 1,
        }
    )
    with _factory()() as session:
        assert session.query(PolicyModuleDecision).count() == 0


def test_workspace_default_link_resolves_when_product_unset(
    hook_env: None,
) -> None:
    dp_id = _seed_dp("hook", "ws_default")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="ws_only_block",
        cedar_source='forbid(principal, action == Action::"read", resource);',
        created_by_user_id=None,
    )
    from pointlessql.services.policy_as_code import link_modules_to_workspace

    link_modules_to_workspace(
        _factory(),
        workspace_id=1,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    with pytest.raises(PermissionDeniedError):
        run_before_read(
            {
                "full_name": "hook.ws_default.foo",
                "principal": {"id": 1, "email": "a@b.test"},
                "authoring_product_id": dp_id,
                "workspace_id": 1,
            }
        )


def test_decision_persistence_carries_principal_and_resource(
    hook_env: None,
) -> None:
    dp_id = _seed_dp("hook", "audit_trail")
    module = create_module(
        _factory(),
        workspace_id=1,
        name="permit_for_audit",
        cedar_source='permit(principal, action == Action::"read", resource);',
        created_by_user_id=None,
    )
    link_modules_to_product(
        _factory(),
        data_product_id=dp_id,
        module_ids=[int(module["id"])],
        updated_by_user_id=None,
    )
    run_before_read(
        {
            "full_name": "hook.audit_trail.metrics",
            "principal": {"id": 17, "email": "a@b.test"},
            "authoring_product_id": dp_id,
            "workspace_id": 1,
        }
    )
    with _factory()() as session:
        row = session.query(PolicyModuleDecision).one()
        assert row.principal_user_id == 17
        assert row.resource_type == "DataProduct"
        assert row.resource_id == "hook.audit_trail"
        assert row.action == "read"
