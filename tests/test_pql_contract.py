"""Tests for the Phase-73.2 ``pql.contract()`` inline DSL + routes.

Covers:

* ``pql.contract(...)`` builds a valid ``DataProductContract``.
* ``DraftContract.yaml()`` round-trips through ``yaml.safe_load``
  + pydantic re-validation.
* ``DraftContract.save()`` writes a file (+ optionally a DB row).
* Invalid table-column spec → pydantic ValidationError.
* Identical saves are idempotent (UNIQUE on
  ``(workspace, catalog, schema, yaml_hash)``).
* POST ``/api/contracts/draft`` returns preview + would_write_path.
* POST ``/api/contracts/save`` writes file + inserts row.
* GET ``/api/contracts/drafts`` returns saved drafts.
* POST ``/api/contracts/drafts/{id}/promote`` copies into the
  active search path and loads the contract.
* Promote non-existent draft → 404.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products._schema import DataProductContract
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.pql import contract as pql_contract


def test_contract_dsl_builds_valid_payload() -> None:
    """``pql.contract(...)`` returns a builder with a validated contract."""
    draft = pql_contract(
        "main",
        "sales_gold",
        tables=[
            {
                "name": "orders",
                "columns": [{"name": "id", "type": "long", "nullable": False}],
                "primary_key": ["id"],
            }
        ],
        description="curated orders",
    )
    assert draft.contract.catalog == "main"
    assert draft.contract.schema_name == "sales_gold"
    assert draft.contract.tables[0].name == "orders"


def test_contract_dsl_round_trips_through_yaml() -> None:
    """``.yaml()`` round-trips through pydantic re-validation."""
    draft = pql_contract(
        "main",
        "sales_gold",
        tables=[
            {"name": "orders", "columns": [{"name": "id", "type": "long"}]},
        ],
        description="curated orders",
    )
    payload = yaml.safe_load(draft.yaml())
    inner = payload["data_product"]
    reparsed = DataProductContract.model_validate(inner)
    assert reparsed == draft.contract


def test_contract_dsl_rejects_unknown_type() -> None:
    """Unknown column type raises pydantic ``ValidationError``."""
    with pytest.raises(ValidationError):
        pql_contract(
            "main",
            "sales_gold",
            tables=[{"name": "orders", "columns": [{"name": "id", "type": "what"}]}],
            description="",
        )


def test_save_writes_file_and_inserts_row(tmp_path: Path) -> None:
    """``.save()`` writes yaml and inserts a DataProductYamlDraft row."""
    factory = app.state.session_factory
    draft = pql_contract(
        "main",
        "sales_gold",
        tables=[{"name": "orders", "columns": [{"name": "id", "type": "long"}]}],
        description="curated orders",
    )
    written = draft.save(
        session_factory=factory,
        draft_dir=tmp_path,
        workspace_id=1,
        created_by_user_id=1,
    )
    assert written.exists()
    with factory() as session:
        row = session.execute(select(DataProductYamlDraft)).scalar_one()
        assert row.source_kind == "pql_contract"
        assert row.workspace_id == 1


def test_save_is_idempotent(tmp_path: Path) -> None:
    """Two saves of identical content collapse onto one row."""
    factory = app.state.session_factory
    for _ in range(2):
        draft = pql_contract(
            "main",
            "sales_gold",
            tables=[{"name": "orders", "columns": [{"name": "id", "type": "long"}]}],
            description="curated orders",
        )
        draft.save(
            session_factory=factory,
            draft_dir=tmp_path,
            workspace_id=1,
            created_by_user_id=1,
        )
    with factory() as session:
        rows = session.execute(select(DataProductYamlDraft)).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_preview_route(admin_client: httpx.AsyncClient) -> None:
    """POST /api/contracts/draft returns preview + target path."""
    res = await admin_client.post(
        "/api/contracts/draft",
        json={
            "catalog": "main",
            "schema": "sales_gold",
            "description": "curated orders",
            "tables": [
                {
                    "name": "orders",
                    "columns": [{"name": "id", "type": "long"}],
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "yaml_preview" in body
    assert "would_write_path" in body
    assert body["validated"]["catalog"] == "main"


@pytest.mark.asyncio
async def test_draft_preview_invalid_400(
    admin_client: httpx.AsyncClient,
) -> None:
    """Missing required field → 400."""
    res = await admin_client.post(
        "/api/contracts/draft",
        json={"catalog": "main"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_save_route_creates_row(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/contracts/save persists the file + DB row."""
    monkeypatch.setattr(app.state.settings.data_products, "draft_dir", tmp_path)
    res = await admin_client.post(
        "/api/contracts/save",
        json={
            "catalog": "main",
            "schema": "sales_gold",
            "description": "curated orders",
            "tables": [
                {
                    "name": "orders",
                    "columns": [{"name": "id", "type": "long"}],
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert Path(body["draft_path"]).exists()


@pytest.mark.asyncio
async def test_drafts_list_route(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/contracts/drafts lists saved drafts."""
    monkeypatch.setattr(app.state.settings.data_products, "draft_dir", tmp_path)
    await admin_client.post(
        "/api/contracts/save",
        json={
            "catalog": "main",
            "schema": "sales_gold",
            "description": "x",
            "tables": [{"name": "t", "columns": [{"name": "id", "type": "long"}]}],
        },
    )
    res = await admin_client.get("/api/contracts/drafts")
    assert res.status_code == 200
    body = res.json()
    assert len(body["drafts"]) == 1
    assert body["drafts"][0]["catalog_name"] == "main"


@pytest.mark.asyncio
async def test_promote_draft_loads_contract(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST .../promote copies into the search path + loads the contract."""
    draft_dir = tmp_path / "drafts"
    active_dir = tmp_path / "active"
    active_dir.mkdir(parents=True)
    monkeypatch.setattr(app.state.settings.data_products, "draft_dir", draft_dir)
    monkeypatch.setattr(
        app.state.settings.data_products, "yaml_search_paths", [active_dir]
    )

    save_res = await admin_client.post(
        "/api/contracts/save",
        json={
            "catalog": "main",
            "schema": "sales_gold",
            "description": "x",
            "tables": [{"name": "t", "columns": [{"name": "id", "type": "long"}]}],
        },
    )
    draft_id = save_res.json()["draft_id"]

    res = await admin_client.post(f"/api/contracts/drafts/{draft_id}/promote")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["promoted_to_data_product_id"] is not None
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        assert dp.catalog_name == "main"
        row = session.execute(
            select(DataProductYamlDraft).where(
                DataProductYamlDraft.id == draft_id
            )
        ).scalar_one()
        assert row.promoted_at is not None


@pytest.mark.asyncio
async def test_promote_unknown_draft_404(
    admin_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Promote on a non-existent draft id → 404."""
    monkeypatch.setattr(
        app.state.settings.data_products, "yaml_search_paths", [tmp_path]
    )
    res = await admin_client.post("/api/contracts/drafts/99999/promote")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_discard_draft_route(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST .../discard stamps discarded_at."""
    monkeypatch.setattr(app.state.settings.data_products, "draft_dir", tmp_path)
    save_res = await admin_client.post(
        "/api/contracts/save",
        json={
            "catalog": "main",
            "schema": "sales_gold",
            "description": "x",
            "tables": [{"name": "t", "columns": [{"name": "id", "type": "long"}]}],
        },
    )
    draft_id = save_res.json()["draft_id"]
    res = await admin_client.post(f"/api/contracts/drafts/{draft_id}/discard")
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(DataProductYamlDraft, draft_id)
        assert row is not None
        assert row.discarded_at is not None
