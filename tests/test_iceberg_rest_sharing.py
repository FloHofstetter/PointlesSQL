"""Tests for the Iceberg REST OpenSharing connection hints."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.services import iceberg_rest_sharing


def test_hints_cover_each_engine() -> None:
    hints = iceberg_rest_sharing.iceberg_rest_connection_hints(
        catalog_uri="https://host/iceberg/v1", share="sales_share", token="tok-123"
    )
    engines = {h["engine"] for h in hints}
    assert engines == {"trino", "spark", "pyiceberg", "flink", "snowflake"}
    for hint in hints:
        assert {"engine", "title", "language", "snippet"} <= set(hint)
        # Every snippet wires the share's catalog URI + warehouse + token.
        assert "https://host/iceberg/v1" in hint["snippet"]
        assert "sales_share" in hint["snippet"]
        assert "tok-123" in hint["snippet"]


def test_hints_use_placeholder_without_token() -> None:
    hints = iceberg_rest_sharing.iceberg_rest_connection_hints(
        catalog_uri="https://host/iceberg/v1", share="s"
    )
    assert all("<your-recipient-token>" in h["snippet"] for h in hints)


@pytest.mark.asyncio
async def test_route_returns_hints(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/sharing/shares/demo_share/iceberg-rest")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["share"] == "demo_share"
    assert data["catalog_uri"].endswith("/iceberg/v1")
    assert {h["engine"] for h in data["hints"]} >= {"trino", "spark", "snowflake"}


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/sharing/shares/demo_share/iceberg-rest")
    assert resp.status_code in {401, 403}
