"""Schema-versioning enforcer + bumper integration (Phase 144)."""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductOutputPort,
    OutputPortSchemaVersion,
)
from pointlessql.services.schema_versioning import (
    SchemaBreakingChangeError,
    assert_schema_compatibility,
    bump_port_version,
    compute_diff,
    propose_bump,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product_with_port(name: str) -> tuple[int, int]:
    contract = {"name": name, "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="sv",
            schema_name=name,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(dp)
        session.commit()
        port = DataProductOutputPort(
            data_product_id=dp.id,
            name="sql",
            kind="sql",
            description=None,
            format=None,
            location=None,
            identity_requirements=None,
            version_semver="0.1.0",
            created_at=_now(),
        )
        session.add(port)
        session.commit()
        return int(dp.id), int(port.id)


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(OutputPortSchemaVersion).delete()
        session.query(DataProductOutputPort).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def _schema(*cols) -> dict:
    return {
        "columns": [
            {"name": n, "type": t, "nullable": nul, "description": ""}
            for n, t, nul in cols
        ]
    }


def test_propose_bump_major() -> None:
    old = _schema(("id", "Int", False))
    new = _schema(("id", "Int", False), ("email", "String", False))
    diff = compute_diff(old, new)
    next_semver, kind = propose_bump("0.1.0", diff)
    assert kind == "major"
    assert next_semver == "1.0.0"


def test_propose_bump_minor_increments_minor() -> None:
    diff = compute_diff(
        _schema(("id", "Int", False)),
        _schema(("id", "Int", False), ("email", "String", True)),
    )
    next_semver, kind = propose_bump("0.1.0", diff)
    assert kind == "minor"
    assert next_semver == "0.2.0"


def test_propose_bump_patch_increments_patch() -> None:
    old = {"columns": [{"name": "id", "type": "Int", "nullable": False, "description": "old"}]}
    new = {"columns": [{"name": "id", "type": "Int", "nullable": False, "description": "new"}]}
    diff = compute_diff(old, new)
    next_semver, kind = propose_bump("1.4.7", diff)
    assert kind == "patch"
    assert next_semver == "1.4.8"


def test_propose_bump_no_change_returns_current() -> None:
    same = _schema(("id", "Int", False))
    diff = compute_diff(same, same)
    next_semver, kind = propose_bump("2.3.1", diff)
    assert kind == "none"
    assert next_semver == "2.3.1"


def test_block_mode_raises_on_breaking_change() -> None:
    dp_id, port_id = _seed_product_with_port("block")
    bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False), ("email", "String", True)),
        change_summary="initial",
    )
    breaking = _schema(("id", "Int", False))
    with pytest.raises(SchemaBreakingChangeError):
        assert_schema_compatibility(
            _factory(),
            data_product_id=dp_id,
            table_name=None,
            new_schema=breaking,
            mode="block",
        )


def test_warn_mode_returns_outcome_without_raising() -> None:
    dp_id, port_id = _seed_product_with_port("warn")
    bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False), ("email", "String", True)),
    )
    breaking = _schema(("id", "Int", False))
    outcome = assert_schema_compatibility(
        _factory(),
        data_product_id=dp_id,
        table_name=None,
        new_schema=breaking,
        mode="warn",
    )
    assert outcome is not None
    assert outcome.diff.change_kind == "major"


def test_off_mode_returns_none() -> None:
    dp_id, _ = _seed_product_with_port("off")
    outcome = assert_schema_compatibility(
        _factory(),
        data_product_id=dp_id,
        table_name=None,
        new_schema=_schema(("anything", "String", True)),
        mode="off",
    )
    assert outcome is None


def test_no_port_returns_none() -> None:
    contract = {"name": "x", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="sv",
            schema_name="empty",
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(dp)
        session.commit()
        dp_id = int(dp.id)
    outcome = assert_schema_compatibility(
        _factory(),
        data_product_id=dp_id,
        table_name=None,
        new_schema=_schema(("id", "Int", False)),
        mode="block",
    )
    assert outcome is None


def test_bump_port_version_advances_port_semver() -> None:
    _, port_id = _seed_product_with_port("advance")
    bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False)),
        change_summary="first",
    )
    bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False), ("email", "String", True)),
        change_summary="minor",
    )
    with _factory()() as session:
        port = session.get(DataProductOutputPort, port_id)
        assert port is not None
        assert port.version_semver != "0.1.0"


def test_bump_with_no_change_returns_current_row() -> None:
    _, port_id = _seed_product_with_port("noop")
    one, _ = bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False)),
    )
    two, diff = bump_port_version(
        _factory(),
        output_port_id=port_id,
        new_schema=_schema(("id", "Int", False)),
    )
    assert diff.change_kind == "none"
    assert one["version_semver"] == two["version_semver"]
