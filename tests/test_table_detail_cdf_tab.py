"""Tests for the CDF events tab on the table-detail page."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import CdfTailEvent, CdfTailSubscription
from pointlessql.services.unitycatalog import UnityCatalogClient


def _authed_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _stub_uc_client_for_table(monkeypatch: pytest.MonkeyPatch, full_name: str) -> None:
    """Replace ``app.state.uc_client`` + ``for_principal`` with a stub.

    Returns nothing; mutates app.state in-place AND monkeypatches the
    classmethod constructor so principal-bound requests (cookie-auth
    flows) also get the stub instead of building a real per-principal
    client.
    """
    catalog, schema, table = full_name.split(".", 2)
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": table,
            "catalog_name": catalog,
            "schema_name": schema,
            "full_name": full_name,
            "table_type": "EXTERNAL",
            "data_source_format": "DELTA",
            "comment": None,
            "owner": None,
            "table_id": "test-table-id",
            "created_at": None,
            "created_by": None,
            "updated_at": None,
            "updated_by": None,
            "storage_location": "/tmp/test",
            "properties": {},
            "columns": [{"name": "id", "type_text": "int", "comment": None}],
        }
    )
    client.get_tags = AsyncMock(return_value=[])
    client.get_permissions = AsyncMock(return_value=[])
    client.get_effective_permissions = AsyncMock(
        return_value=[
            {
                "principal": "admin@pql.test",
                "privilege": "SELECT",
                "scope": "table",
                "resource": full_name,
            }
        ]
    )
    client.get_lineage = AsyncMock(
        return_value={
            "upstream": {"nodes": [], "edges": []},
            "downstream": {"nodes": [], "edges": []},
        }
    )
    app.state.uc_client = client
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),
    )


def _seed_subscription(table: str, *, is_active: bool = True) -> int:
    factory = app.state.session_factory
    with factory() as session:
        sub = CdfTailSubscription(
            workspace_id=1,
            table_full_name=table,
            row_id_column="id",
            producer_label=f"cdf-tail:{table}",
            is_active=is_active,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub.id


def _seed_event(sub_id: int, table: str, *, version: int, row_id: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        ev = CdfTailEvent(
            workspace_id=1,
            subscription_id=sub_id,
            table_full_name=table,
            delta_version=version,
            row_id=row_id,
            change_type="insert",
            producer_label=f"cdf-tail:{table}",
            commit_timestamp=datetime.datetime.now(datetime.UTC),
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ev)
        session.commit()


class TestCdfTabVisibility:
    """Tab is conditional on a workspace-scoped subscription."""

    @pytest.mark.asyncio
    async def test_table_without_subscription_omits_tab(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        full_name = "demo.silver.no_sub_table"
        _stub_uc_client_for_table(monkeypatch, full_name)
        async with _authed_client() as c:
            resp = await c.get("/catalogs/demo/schemas/silver/tables/no_sub_table")
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert 'id="tab-cdf-events"' not in body
        assert 'id="tab-cdf-events-btn"' not in body

    @pytest.mark.asyncio
    async def test_table_with_subscription_renders_recent_events(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        full_name = "demo.silver.tracked_table"
        sub_id = _seed_subscription(full_name)
        _seed_event(sub_id, full_name, version=0, row_id="42")
        _seed_event(sub_id, full_name, version=1, row_id="43")
        _stub_uc_client_for_table(monkeypatch, full_name)
        async with _authed_client() as c:
            resp = await c.get("/catalogs/demo/schemas/silver/tables/tracked_table")
        assert resp.status_code == 200, resp.text
        body = resp.text
        # Tab + pane mounted.
        assert 'id="tab-cdf-events"' in body
        assert 'id="tab-cdf-events-btn"' in body
        # Subscription metadata surfaces in the pane.
        assert f"cdf-tail:{full_name}" in body
        # Both events rendered.
        assert ">42<" in body
        assert ">43<" in body
        # Insert change-type pill.
        assert "insert" in body
