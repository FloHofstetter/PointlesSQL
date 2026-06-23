"""Governance masking is wired at every real consumer access point.

The masking sidecar is unit-tested as a pure function elsewhere; these
tests guard the *wiring* — a regression in any route could silently ship
cleartext PII. For each access point (catalog preview, data-product export
port, and the SQL SELECT dispatcher) a classified ``email`` column is
masked for a non-privileged viewer and returned in the clear for a
privileged one (admin, or — for the viewer_sees_clear paths — the product
steward).
"""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pandas as pd
import pytest
import sqlglot
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, User
from pointlessql.services import governance as gov

_CLEAR_EMAIL = "alice@example.com"
_MASKED_EMAIL = "***@***.***"


def _factory() -> Any:
    return app.state.session_factory


def _user_id(email: str) -> int:
    with _factory()() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None, email
        return user.id


def _seed_product_with_pii(schema: str, *, steward_email: str | None = None) -> int:
    """Seed a one-table product whose ``email`` column is classified PII."""
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"main.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": "main",
        "schema_name": schema,
        "tables": [{"name": "people", "columns": [{"name": "email", "type": "string"}]}],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name="main",
            schema_name=schema,
            steward_user_id=_user_id(steward_email) if steward_email else None,
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
        dp_id = row.id
    gov.add_classification(
        _factory(),
        data_product_id=dp_id,
        catalog="main",
        schema=schema,
        table="people",
        column="email",
        classification="pii",
    )
    # The routes consult classifications_for_schema; confirm it derives the
    # partial strategy for the pii column so the masking has something to do.
    index = gov.classifications_for_schema(_factory(), catalog="main", schema=schema)
    assert index[("people", "email")][1] == "partial"
    return dp_id


@pytest.fixture
def pii_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``PQL.table`` return a one-row PII frame (preview + export read)."""
    from pointlessql.pql import PQL

    monkeypatch.setattr(
        PQL,
        "table",
        lambda self, full_name: pd.DataFrame({"email": [_CLEAR_EMAIL], "id": [1]}),
    )


def _grant_select(stub: Any) -> None:
    """Configure the UC stub so both test principals hold SELECT."""
    stub.get_effective_permissions = AsyncMock(
        return_value=[
            {"principal": "test@test.com", "privileges": ["SELECT"]},
            {"principal": "nonadmin@test.com", "privileges": ["SELECT"]},
        ]
    )
    stub.get_table = AsyncMock(return_value={})


async def _preview(client: httpx.AsyncClient, schema: str) -> list[list[Any]]:
    resp = await client.get(
        f"/api/catalogs/main/schemas/{schema}/tables/people/preview",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["rows"]


# --- Access point 1: catalog preview ---------------------------------------


async def test_preview_masks_for_non_admin(
    pii_frame: None,
    uc_client_stub: Any,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-steward, non-admin viewer gets the email masked in the preview."""
    _grant_select(uc_client_stub)
    _seed_product_with_pii("gov_prev_mask")

    rows = await _preview(non_admin_client, "gov_prev_mask")

    assert rows[0][0] == _MASKED_EMAIL


async def test_preview_clear_for_admin(
    pii_frame: None,
    uc_client_stub: Any,
    admin_client: httpx.AsyncClient,
) -> None:
    """An admin viewer sees the email in the clear."""
    _grant_select(uc_client_stub)
    _seed_product_with_pii("gov_prev_admin")

    rows = await _preview(admin_client, "gov_prev_admin")

    assert rows[0][0] == _CLEAR_EMAIL


async def test_preview_clear_for_steward_bypass(
    pii_frame: None,
    uc_client_stub: Any,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """viewer_sees_clear: the product steward (non-admin) bypasses masking."""
    _grant_select(uc_client_stub)
    _seed_product_with_pii("gov_prev_steward", steward_email="nonadmin@test.com")

    rows = await _preview(non_admin_client, "gov_prev_steward")

    assert rows[0][0] == _CLEAR_EMAIL


# --- Access point 2: data-product export port ------------------------------


async def _export_csv(client: httpx.AsyncClient, schema: str) -> str:
    resp = await client.get(
        f"/api/data-products/main/{schema}/export",
        params={"table": "people", "format": "csv"},
    )
    assert resp.status_code == 200, resp.text
    return resp.text


async def test_export_masks_for_non_admin(
    pii_frame: None,
    uc_client_stub: Any,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """The export port redacts the classified column for a non-privileged user."""
    _grant_select(uc_client_stub)
    _seed_product_with_pii("gov_exp_mask")

    body = await _export_csv(non_admin_client, "gov_exp_mask")

    assert _MASKED_EMAIL in body
    assert _CLEAR_EMAIL not in body


async def test_export_clear_for_admin(
    pii_frame: None,
    uc_client_stub: Any,
    admin_client: httpx.AsyncClient,
) -> None:
    """An admin export carries cleartext."""
    _grant_select(uc_client_stub)
    _seed_product_with_pii("gov_exp_admin")

    body = await _export_csv(admin_client, "gov_exp_admin")

    assert _CLEAR_EMAIL in body


# --- Access point 3: SQL SELECT dispatcher ---------------------------------


def _dispatch_ctx(schema: str, *, is_admin: bool) -> Any:
    from types import SimpleNamespace

    from pointlessql.api.sql._dispatcher._types import DispatchContext
    from pointlessql.pql import StmtType

    sql = f"SELECT email FROM main.{schema}.people"
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))
    return DispatchContext(
        request=request,  # type: ignore[arg-type]
        settings=app.state.settings,
        sql=sql,
        ast=sqlglot.parse_one(sql),
        stype=StmtType.SELECT,
        actor_email="test@test.com" if is_admin else "nonadmin@test.com",
        is_admin=is_admin,
        conn=None,
        max_rows=100,
    )


def _patch_dispatch(monkeypatch: pytest.MonkeyPatch, schema: str) -> None:
    """Stub the privilege + execution layers so only masking is exercised."""
    from pointlessql.api.sql._dispatcher import _select as select_mod

    full = f"main.{schema}.people"

    async def _approved(_ctx: Any, _refs: Any) -> tuple[dict[str, str], dict[str, Any]]:
        return ({full: "/tmp/loc"}, {})

    monkeypatch.setattr(select_mod, "enforce_select_with_policies", _approved)
    monkeypatch.setattr(select_mod, "get_authoring_product", lambda _req: None)

    from types import SimpleNamespace

    from pointlessql.api.sql import editor as editor_mod

    def _run_sql_sync(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            rows=[[_CLEAR_EMAIL]],
            columns=["email"],
            row_count=1,
            truncated=False,
            duration_ms=1,
            executed_sql=f"SELECT email FROM {full}",
            referenced_tables=[full],
        )

    monkeypatch.setattr(editor_mod, "run_sql_sync", _run_sql_sync)


async def test_sql_dispatcher_masks_for_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SELECT dispatcher masks a classified result column for non-admins."""
    from pointlessql.api.sql._dispatcher._select import execute_select

    schema = "gov_sql_mask"
    _seed_product_with_pii(schema)
    _patch_dispatch(monkeypatch, schema)

    result = await execute_select(_dispatch_ctx(schema, is_admin=False))

    assert result.rows is not None
    assert result.rows[0][0] == _MASKED_EMAIL


async def test_sql_dispatcher_clear_for_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """An admin SELECT bypasses masking (the dispatcher gates on is_admin)."""
    from pointlessql.api.sql._dispatcher._select import execute_select

    schema = "gov_sql_admin"
    _seed_product_with_pii(schema)
    _patch_dispatch(monkeypatch, schema)

    result = await execute_select(_dispatch_ctx(schema, is_admin=True))

    assert result.rows is not None
    assert result.rows[0][0] == _CLEAR_EMAIL
