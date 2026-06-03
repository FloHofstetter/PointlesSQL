"""Tests for the wired Lens ``query`` executor.

The executor reads each referenced Delta table from its resolved
storage location, masks classified columns at the source, registers the
masked frame into an in-process DuckDB, and runs the gated SELECT.  We
exercise it with a real on-disk Delta table and a fake UC client that
resolves the location + answers privilege checks, so no soyuz server is
needed.  The ``uc_client=None`` path (unit-test / detached) must keep
returning the gated SQL with no rows.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import deltalake
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.config import Settings
from pointlessql.models import DataProduct, User
from pointlessql.services import governance as gov
from pointlessql.services.lens.tools._base import LensToolError, SessionContext
from pointlessql.services.lens.tools.query import QueryArgs, _execute_query


def _factory():
    return app.state.session_factory


def _user_id(email: str) -> int:
    with _factory()() as session:
        return int(session.scalar(select(User.id).where(User.email == email)))


def _settings() -> Settings:
    return getattr(app.state, "settings", None) or Settings()


def _write_delta(path: Path) -> None:
    """Seed a tiny Delta table with a clear + a PII-ish column."""
    frame = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["Ann", "Bo", "Cy"],
            "email": ["ann@x.io", "bo@x.io", "cy@x.io"],
        }
    )
    deltalake.write_deltalake(str(path), frame)


def _seed_dp(catalog: str, schema: str) -> int:
    """Insert a minimal DataProduct row so a classification can attach."""
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
            steward_user_id=None,
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
        return int(row.id)


class _FakeUC:
    """Minimal UC facade: resolves one location + canned grants."""

    def __init__(self, location: str, grants: dict[str, list[str]] | None = None) -> None:
        self._location = location
        self._grants = grants or {}

    async def get_table(self, catalog: str, schema: str, table: str) -> dict[str, Any]:
        return {"storage_location": self._location}

    async def get_effective_permissions(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        return [{"principal": p, "privileges": privs} for p, privs in self._grants.items()]


def _ctx(uc_client: Any, *, email: str) -> SessionContext:
    return SessionContext(
        workspace_id=1,
        user_id=_user_id(email),
        lens_session_id=None,
        factory=_factory(),
        settings=_settings(),
        uc_client=uc_client,
    )


@pytest.mark.asyncio
async def test_query_no_uc_client_returns_gated_sql_only() -> None:
    """Without a live client the tool gates only — LIMIT injected, no rows."""
    ctx = _ctx(None, email="test@test.com")
    out = await _execute_query(ctx, QueryArgs(sql="SELECT 1 FROM main.silver.t"))
    assert "LIMIT" in out.executed_sql.upper()
    assert out.rows == []
    assert out.row_count == 0


@pytest.mark.asyncio
async def test_query_executes_against_delta_for_admin(tmp_path: Path) -> None:
    """Admin runs a real SELECT and gets back unmasked rows + columns."""
    loc = tmp_path / "orders"
    _write_delta(loc)
    ctx = _ctx(_FakeUC(str(loc)), email="test@test.com")  # admin → bypass priv check
    out = await _execute_query(
        ctx, QueryArgs(sql="SELECT id, email FROM demo.sales.orders ORDER BY id")
    )
    assert [c.name for c in out.columns] == ["id", "email"]
    assert out.rows == [[1, "ann@x.io"], [2, "bo@x.io"], [3, "cy@x.io"]]
    assert "LIMIT" in out.executed_sql.upper()


@pytest.mark.asyncio
async def test_query_masks_classified_column_through_aggregation(tmp_path: Path) -> None:
    """A non-admin's classified column stays masked even through GROUP BY."""
    loc = tmp_path / "orders"
    _write_delta(loc)
    dp_id = _seed_dp("demo", "salesmask")
    gov.add_classification(
        _factory(),
        data_product_id=dp_id,
        catalog="demo",
        schema="salesmask",
        table="orders",
        column="email",
        classification="pii",
    )
    fake = _FakeUC(str(loc), grants={"nonadmin@test.com": ["SELECT"]})
    ctx = _ctx(fake, email="nonadmin@test.com")
    out = await _execute_query(
        ctx,
        QueryArgs(
            sql="SELECT email, COUNT(*) AS n FROM demo.salesmask.orders GROUP BY email"
        ),
    )
    emails = [row[0] for row in out.rows]
    # masking ran at the source, so no cleartext address survives the aggregation
    assert emails  # rows came back
    for original in ("ann@x.io", "bo@x.io", "cy@x.io"):
        assert original not in emails


@pytest.mark.asyncio
async def test_query_denies_table_without_select(tmp_path: Path) -> None:
    """A non-admin without SELECT gets a typed access-denied tool error."""
    loc = tmp_path / "orders"
    _write_delta(loc)
    fake = _FakeUC(str(loc), grants={})  # no privileges for anyone
    ctx = _ctx(fake, email="nonadmin@test.com")
    with pytest.raises(LensToolError) as excinfo:
        await _execute_query(
            ctx, QueryArgs(sql="SELECT id FROM demo.sales.orders")
        )
    assert excinfo.value.status == "access_denied"
