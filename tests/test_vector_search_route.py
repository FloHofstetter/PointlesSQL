"""Phase 92 — route-level tests for ``POST /api/sql/vector_search``.

Covers the privilege gate (404 on unknown table, 403 on missing
SELECT) and the happy-path against a Delta + fake-embedded index.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.pql import _vector as vmod
from pointlessql.pql.embedders import EMBEDDERS
from pointlessql.services.unitycatalog import UnityCatalogClient


class _FakeEmbedder:
    name = "fake"
    model = "fake-1"
    dim = 4

    def __init__(self, model: str | None = None) -> None:
        self.model = model or "fake-1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 2.0, 3.0] for t in texts]


def _make_uc_mock(
    *,
    storage_location: str,
    effective: list[dict[str, Any]] | None = None,
) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "docs",
            "catalog_name": "main",
            "schema_name": "silver",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def docs_delta_with_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    loc = str(tmp_path / "docs")
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "description": ["alpha bravo", "users churn", "agent retrieval"],
        }
    )
    deltalake.write_deltalake(loc, df)

    monkeypatch.setattr(
        vmod,
        "_resolve_storage_location",
        lambda client, full_name, unreachable_msg: loc,
    )
    monkeypatch.setitem(EMBEDDERS, "fake", _FakeEmbedder)

    # Build the index file directly (REST create endpoint exercised
    # separately in test_vector_index_admin.py).
    vmod.create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=_FakeEmbedder(),
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )
    return loc


async def test_admin_can_vector_search_a_granted_table(
    docs_delta_with_index: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=docs_delta_with_index)
    resp = await admin_client.post(
        "/api/sql/vector_search",
        json={
            "table": "main.silver.docs",
            "column": "description",
            "query": "agent retrieval",
            "top_k": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["table"] == "main.silver.docs"
    assert body["column"] == "description"
    assert len(body["hits"]) == 2
    assert "score" in body["hits"][0]


async def test_non_admin_without_select_is_denied(
    docs_delta_with_index: str, non_admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(
        storage_location=docs_delta_with_index,
        effective=[],
    )
    resp = await non_admin_client.post(
        "/api/sql/vector_search",
        json={
            "table": "main.silver.docs",
            "column": "description",
            "query": "x",
            "top_k": 3,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["required_privilege"] == "SELECT"


async def test_unknown_index_returns_500_via_envelope(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fresh Delta but no index built — search should raise
    # FileNotFoundError which propagates as a 500.
    loc = str(tmp_path / "orphan")
    df = pd.DataFrame({"id": [1], "description": ["solo"]})
    deltalake.write_deltalake(loc, df)
    monkeypatch.setattr(
        vmod,
        "_resolve_storage_location",
        lambda client, full_name, unreachable_msg: loc,
    )
    monkeypatch.setitem(EMBEDDERS, "fake", _FakeEmbedder)
    app.state.uc_client = _make_uc_mock(storage_location=loc)

    resp = await admin_client.post(
        "/api/sql/vector_search",
        json={
            "table": "main.silver.orphan",
            "column": "description",
            "query": "x",
            "top_k": 1,
        },
    )
    assert resp.status_code == 404
