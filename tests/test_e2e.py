"""End-to-end smoke tests for the full PointlesSQL stack.

These tests require a **live** soyuz-catalog server on localhost:8080
and are marked ``integration`` so the default test run skips them.

Run with::

    uv run pytest tests/test_e2e.py -m integration
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings


@pytest.mark.integration
class TestE2ESmoke:
    @pytest.fixture(autouse=True)
    def _setup_app(self, e2e_env: dict[str, Any]) -> None:
        """Wire app.state with a real UnityCatalogClient (no lifespan)."""
        self.env = e2e_env
        client = make_soyuz_client()
        app.state.uc_client = UnityCatalogClient(client)
        app.state.settings = Settings(jupyter_enabled=False)
        app.state.jupyter_process = None

    async def test_full_roundtrip(self) -> None:
        """Create catalog/schema, write table via PQL, verify in web UI."""
        env = self.env
        pql = env["pql"]

        # Write a table via PQL.
        df = pd.DataFrame({
            "id": pd.array([1, 2, 3], dtype="int64"),
            "name": pd.array(["alice", "bob", "charlie"], dtype="object"),
            "score": pd.array([9.5, 8.0, 7.3], dtype="float64"),
        })
        pql.write_table(df, env["full_name"])

        # Verify via web endpoints.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Index page loads without error.
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "alert-danger" not in resp.text

            # Tree API includes the new catalog/schema/table.
            resp = await client.get("/api/tree")
            assert resp.status_code == 200
            tree = resp.json()
            catalog_names = [c["name"] for c in tree]
            assert env["catalog"] in catalog_names

            cat_node = next(c for c in tree if c["name"] == env["catalog"])
            schema_names = [s["name"] for s in cat_node["schemas"]]
            assert env["schema"] in schema_names

            sch_node = next(
                s for s in cat_node["schemas"] if s["name"] == env["schema"]
            )
            table_names = [t["name"] for t in sch_node["tables"]]
            assert env["table"] in table_names

            # Table detail page shows columns and PQL snippet.
            url = (
                f"/catalogs/{env['catalog']}"
                f"/schemas/{env['schema']}"
                f"/tables/{env['table']}"
            )
            resp = await client.get(url)
            assert resp.status_code == 200
            body = resp.text

            # Column names appear in the HTML.
            assert "id" in body
            assert "name" in body
            assert "score" in body

            # PQL snippet card is present.
            assert "PQL Snippet" in body
            assert f'pql.table("{env["full_name"]}")' in body
