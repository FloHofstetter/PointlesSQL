"""Schema-versioning enforcer wired into the before-write hook chain."""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator

import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import PermissionDeniedError
from pointlessql.models import (
    DataProduct,
    DataProductOutputPort,
    DataProductPolicy,
    OutputPortSchemaVersion,
)
from pointlessql.pql._hooks import HookContext, run_before_write
from pointlessql.services.schema_versioning._bootstrap import (
    register_schema_versioning_hooks,
    reset_for_tests,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _wipe() -> None:
    with _factory()() as session:
        session.query(OutputPortSchemaVersion).delete()
        session.query(DataProductOutputPort).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProduct).delete()
        session.commit()


def _seed(breaking_change_policy: str = "warn") -> tuple[int, int]:
    contract = {
        "name": "hook.schema",
        "version": "1.0.0",
        "description": "",
        "catalog": "hook",
        "schema_name": "schema",
        "tables": [],
    }
    with _factory()() as session:
        product = DataProduct(
            workspace_id=1,
            catalog_name="hook",
            schema_name="schema",
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(product)
        session.flush()
        port = DataProductOutputPort(
            data_product_id=int(product.id),
            name="silver",
            kind="sql",
            format="delta",
            location="hook.schema.silver",
            description="",
            version_semver="1.0.0",
            created_at=_now(),
        )
        session.add(port)
        session.flush()
        version = OutputPortSchemaVersion(
            output_port_id=int(port.id),
            version_semver="1.0.0",
            schema_json=json.dumps(
                {
                    "columns": [
                        {"name": "id", "type": "int64", "nullable": False},
                        {"name": "value", "type": "string", "nullable": True},
                    ]
                }
            ),
            bumped_at=_now(),
            bumped_by_user_id=None,
            change_kind="minor",
            change_summary="initial",
        )
        session.add(version)
        policy = DataProductPolicy(
            data_product_id=int(product.id),
            breaking_change_policy=breaking_change_policy,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(policy)
        session.commit()
        return int(product.id), int(port.id)


class _FakeField:
    def __init__(self, type_name: str, nullable: bool) -> None:
        self.type = type_name
        self.nullable = nullable


class _FakeSchema:
    def __init__(self, fields: dict[str, _FakeField]) -> None:
        self._fields = fields
        self.names = list(fields.keys())

    def field(self, index: int) -> _FakeField:
        name = self.names[index]
        return self._fields[name]


class _FakeFrame:
    def __init__(self, fields: dict[str, _FakeField]) -> None:
        self.schema = _FakeSchema(fields)


@pytest.fixture
def schema_hook_env() -> Iterator[None]:
    _wipe()
    reset_for_tests()
    with HookContext():
        register_schema_versioning_hooks(_factory())
        yield
    reset_for_tests()
    _wipe()


def test_register_schema_versioning_hooks_idempotent(schema_hook_env: None) -> None:
    from pointlessql.pql._hooks import registered_counts

    before = registered_counts()["before_write"]
    register_schema_versioning_hooks(_factory())
    assert registered_counts()["before_write"] == before


def test_compatible_write_passes(schema_hook_env: None) -> None:
    product_id, _port = _seed(breaking_change_policy="block")
    frame = _FakeFrame(
        {
            "id": _FakeField("int64", False),
            "value": _FakeField("string", True),
        }
    )
    run_before_write(frame, {
        "authoring_product_id": product_id,
        "workspace_id": 1,
    })


def test_breaking_write_blocked_under_strict_policy(schema_hook_env: None) -> None:
    product_id, _port = _seed(breaking_change_policy="block")
    frame = _FakeFrame(
        {
            "id": _FakeField("int64", False),
            # ``value`` removed → major-breaking
        }
    )
    with pytest.raises(PermissionDeniedError):
        run_before_write(frame, {
            "authoring_product_id": product_id,
            "workspace_id": 1,
        })


def test_missing_frame_skips_hook(schema_hook_env: None) -> None:
    product_id, _port = _seed(breaking_change_policy="block")
    # Cedar fires the same chain with frame=None; the schema hook must
    # not raise on absent frames so unrelated callers stay unaffected.
    run_before_write(None, {
        "authoring_product_id": product_id,
        "workspace_id": 1,
    })
