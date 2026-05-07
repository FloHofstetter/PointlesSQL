"""Phase 51.3 — repo_assets loaders for dashboards + saved queries."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models.catalog import Dashboard, SavedQuery
from pointlessql.repo_assets import (
    load_dashboards_from_yaml,
    load_saved_queries_from_yaml,
)


def _factory(_test_engine: tuple[Engine, sessionmaker]) -> sessionmaker:  # type: ignore[type-arg]
    return _test_engine[1]


_VALID_YAML = """\
dashboards:
  - slug: weekly-orders
    title: Weekly orders
    description: Weekly orders volume.
    notebook_path: dashboards/weekly_orders.py

saved_queries:
  - slug: top-customers
    title: Top customers
    description: Top customers by order_total
    sql_text: |
      SELECT customer_id, SUM(order_total)
      FROM main.sales_gold.orders
      GROUP BY 1
      ORDER BY 2 DESC
      LIMIT 50
    is_shared: true
"""


def test_load_dashboards_from_yaml_inserts_row(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text(_VALID_YAML)
    n = load_dashboards_from_yaml(
        yaml_file, factory=factory, workspace_id=1, owner_user_id=1
    )
    assert n == 1
    with factory() as session:
        rows = list(session.execute(select(Dashboard).where(Dashboard.slug == "weekly-orders")).scalars())
    assert len(rows) == 1
    assert rows[0].title == "Weekly orders"
    assert rows[0].source.startswith("repo:")
    assert rows[0].repo_yaml_path is not None


def test_load_saved_queries_from_yaml_inserts_row(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text(_VALID_YAML)
    n = load_saved_queries_from_yaml(
        yaml_file, factory=factory, workspace_id=1, owner_user_id=1
    )
    assert n == 1
    with factory() as session:
        rows = list(session.execute(select(SavedQuery).where(SavedQuery.slug == "top-customers")).scalars())
    assert len(rows) == 1
    assert rows[0].is_shared is True
    assert rows[0].source.startswith("repo:")


def test_load_dashboards_idempotent_upsert(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text(_VALID_YAML)
    n_first = load_dashboards_from_yaml(
        yaml_file, factory=factory, workspace_id=1, owner_user_id=1
    )
    # Mutate the title in place.
    yaml_file.write_text(_VALID_YAML.replace("Weekly orders", "Weekly orders v2"))
    n_second = load_dashboards_from_yaml(
        yaml_file, factory=factory, workspace_id=1, owner_user_id=1
    )
    assert n_first == n_second == 1
    with factory() as session:
        row = session.execute(
            select(Dashboard).where(Dashboard.slug == "weekly-orders")
        ).scalar_one()
    assert row.title == "Weekly orders v2"


def test_loader_rejects_missing_required_field(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text("dashboards:\n  - slug: bad\n    title: Missing notebook_path\n")
    with pytest.raises(ValidationError, match="notebook_path"):
        load_dashboards_from_yaml(
            yaml_file, factory=factory, workspace_id=1, owner_user_id=1
        )


def test_loader_handles_empty_yaml_blocks(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text("data_product:\n  name: x\n  catalog: c\n  schema: s\n  version: '1'\n  description: ''\n  tables: []\n")
    # No dashboards: / saved_queries: keys → loader is a no-op.
    n_d = load_dashboards_from_yaml(yaml_file, factory=factory, workspace_id=1, owner_user_id=1)
    n_q = load_saved_queries_from_yaml(yaml_file, factory=factory, workspace_id=1, owner_user_id=1)
    assert n_d == 0
    assert n_q == 0


def test_loader_rejects_non_list_block(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    yaml_file = tmp_path / "pointlessql.yaml"
    yaml_file.write_text("dashboards: not-a-list\n")
    with pytest.raises(ValidationError, match="must be a list"):
        load_dashboards_from_yaml(yaml_file, factory=factory, workspace_id=1, owner_user_id=1)


# Path import keeps the module's typing surface honest.
_ = Path
