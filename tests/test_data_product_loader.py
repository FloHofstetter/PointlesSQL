"""Tests for :func:`pointlessql.data_products.load_contract`.

Cover the full happy-path (parse → DB UPSERT → re-load = idempotent),
the steward-FK resolution against ``users`` rows, and the four
fail-loud edges (missing file, malformed yaml, missing required
field, no ``data_product:`` block).

Uses the centralised ``app.state.session_factory`` exposed by
``conftest._auth_db`` (see
``feedback_use_centralized_test_fixtures.md``) — no hand-rolled
engines.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import (
    DataProductContract,
    DataProductYamlInvalid,
    load_contract,
    parse_yaml,
)
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.2.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id,    type: long,      nullable: false}
        - {name: customer_id, type: long,      nullable: false}
        - {name: order_total, type: decimal,   nullable: true}
        - {name: ordered_at,  type: timestamp, nullable: false}
"""


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write *content* to ``tmp_path/pointlessql.yaml`` and return the path."""
    p = tmp_path / "pointlessql.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_yaml_returns_validated_contract(tmp_path: Path) -> None:
    """Valid yaml round-trips through pydantic into a frozen contract."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    contract = parse_yaml(yaml_path)
    assert isinstance(contract, DataProductContract)
    assert contract.name == "Sales Orders"
    assert contract.version == "1.2.0"
    assert contract.catalog == "main"
    assert contract.schema_name == "sales_gold"
    assert contract.steward_email == "alice@example.com"
    assert contract.sla_minutes == 60
    assert len(contract.tables) == 1
    table = contract.tables[0]
    assert table.name == "orders"
    assert table.primary_key == ("order_id",)
    assert len(table.columns) == 4
    assert contract.get_table("orders") is table
    assert contract.get_table("missing") is None


def test_parse_yaml_rejects_missing_file(tmp_path: Path) -> None:
    """A non-existent path raises :class:`FileNotFoundError`."""
    with pytest.raises(FileNotFoundError):
        parse_yaml(tmp_path / "nope.yaml")


def test_parse_yaml_rejects_empty_file(tmp_path: Path) -> None:
    """An empty yaml file raises :class:`DataProductYamlInvalid`."""
    yaml_path = _write_yaml(tmp_path, "")
    with pytest.raises(DataProductYamlInvalid, match="empty"):
        parse_yaml(yaml_path)


def test_parse_yaml_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    """A list at the top level fails fast."""
    yaml_path = _write_yaml(tmp_path, "- one\n- two\n")
    with pytest.raises(DataProductYamlInvalid, match="mapping"):
        parse_yaml(yaml_path)


def test_parse_yaml_rejects_missing_data_product_block(tmp_path: Path) -> None:
    """A yaml without the wrapper key fails fast."""
    yaml_path = _write_yaml(tmp_path, "conventions: {}\n")
    with pytest.raises(DataProductYamlInvalid, match="data_product"):
        parse_yaml(yaml_path)


def test_parse_yaml_surfaces_pydantic_errors(tmp_path: Path) -> None:
    """Missing required fields surface as DataProductYamlInvalid."""
    yaml_path = _write_yaml(
        tmp_path,
        "data_product:\n  name: Foo\n",  # version + description + catalog/schema missing
    )
    with pytest.raises(DataProductYamlInvalid, match="contract validation"):
        parse_yaml(yaml_path)


def test_parse_yaml_rejects_invalid_column_type(tmp_path: Path) -> None:
    """An out-of-vocabulary column type fails validation."""
    yaml_path = _write_yaml(
        tmp_path,
        """\
data_product:
  name: Foo
  version: "1.0.0"
  description: x
  catalog: main
  schema: foo
  tables:
    - name: t
      columns:
        - {name: c, type: xml, nullable: false}
""",
    )
    with pytest.raises(DataProductYamlInvalid):
        parse_yaml(yaml_path)


def test_load_contract_inserts_row(tmp_path: Path) -> None:
    """First load creates a ``data_products`` row scoped to workspace 1."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    factory = app.state.session_factory
    contract = load_contract(yaml_path, factory=factory)
    assert isinstance(contract, DataProductContract)

    with factory() as session:
        rows = session.execute(select(DataProduct)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.workspace_id == 1
        assert row.catalog_name == "main"
        assert row.schema_name == "sales_gold"
        assert row.version == "1.2.0"
        assert row.sla_minutes == 60
        assert len(row.contract_yaml_hash) == 64
        assert row.steward_user_id is None  # alice not seeded


def test_load_contract_resolves_steward_fk(tmp_path: Path) -> None:
    """Steward email matching a ``users.email`` row populates the FK."""
    factory = app.state.session_factory
    with factory() as session:
        seeded = User(
            email="alice@example.com",
            display_name="Alice",
            password_hash=None,
            is_admin=False,
            is_supervisor=False,
            is_auditor=False,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(seeded)
        session.commit()
        alice_id = seeded.id

    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    load_contract(yaml_path, factory=factory)

    with factory() as session:
        row = session.execute(select(DataProduct)).scalar_one()
        assert row.steward_user_id == alice_id


def test_load_contract_is_idempotent(tmp_path: Path) -> None:
    """Re-loading the same yaml UPSERTs in place — still one row."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    factory = app.state.session_factory

    load_contract(yaml_path, factory=factory)
    load_contract(yaml_path, factory=factory)

    with factory() as session:
        count = len(session.execute(select(DataProduct)).scalars().all())
        assert count == 1


def test_load_contract_refreshes_on_yaml_change(tmp_path: Path) -> None:
    """Editing the yaml + re-loading updates version + hash."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)

    bumped = VALID_YAML.replace('version: "1.2.0"', 'version: "2.0.0"')
    yaml_path.write_text(bumped, encoding="utf-8")
    load_contract(yaml_path, factory=factory)

    with factory() as session:
        row = session.execute(select(DataProduct)).scalar_one()
        assert row.version == "2.0.0"


def test_load_contract_workspace_scoped(tmp_path: Path) -> None:
    """Two workspaces with the same UC schema get distinct rows."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    factory = app.state.session_factory

    # Seed a second workspace row so the FK resolves.
    from pointlessql.models import Workspace

    with factory() as session:
        ws2 = Workspace(
            slug="second",
            name="Second",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ws2)
        session.commit()
        ws2_id = ws2.id

    load_contract(yaml_path, factory=factory, workspace_id=1)
    load_contract(yaml_path, factory=factory, workspace_id=ws2_id)

    with factory() as session:
        count = len(session.execute(select(DataProduct)).scalars().all())
        assert count == 2


def test_load_contract_without_factory_skips_db(tmp_path: Path) -> None:
    """``factory=None`` parses + returns without DB side effects."""
    yaml_path = _write_yaml(tmp_path, VALID_YAML)
    contract = load_contract(yaml_path)
    assert isinstance(contract, DataProductContract)

    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProduct)).scalars().all()
        assert rows == []
