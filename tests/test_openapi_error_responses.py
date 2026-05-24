"""OpenAPI exposes the error envelope for plugin-facing routes.

Confirms the ``responses=STANDARD_ERROR_RESPONSES`` decoration on
the 13 plugin-facing routes (audit ×6, lineage ×3, pql-write ×4)
ends up in ``/openapi.json`` so external clients (the Hermes plugin,
soyuz-catalog-client-style codegen, third-party consumers) can
introspect the error envelope shape.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api.main import app


@pytest.mark.asyncio
async def test_audit_routes_declare_error_envelope_in_openapi() -> None:
    """The 6 plugin-facing audit routes expose ``ErrorEnvelope`` $refs."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema: dict[str, Any] = resp.json()

    paths = schema.get("paths", {})
    audit_routes = [
        "/api/audit/summary",
        "/api/audit/timeseries",
        "/api/audit/anomalies",
        "/api/audit/principal-summary",
        "/api/audit/history",
        "/api/audit/inbox",
    ]
    for path in audit_routes:
        assert path in paths, f"missing path: {path}"
        method_block = paths[path].get("get", {})
        responses = method_block.get("responses", {})
        # Every standard error code must be declared.
        assert "401" in responses, f"{path} missing 401"
        assert "403" in responses, f"{path} missing 403"
        assert "404" in responses, f"{path} missing 404"
        assert "422" in responses, f"{path} missing 422"


@pytest.mark.asyncio
async def test_lineage_routes_declare_error_envelope_in_openapi() -> None:
    """Lineage row-trace / column-trace / value-changes expose envelope."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get("/openapi.json")
    schema: dict[str, Any] = resp.json()
    paths = schema.get("paths", {})
    for path in (
        "/api/lineage/row-trace",
        "/api/lineage/column-trace",
        "/api/lineage/value-changes",
    ):
        assert path in paths, f"missing path: {path}"
        responses = paths[path]["get"]["responses"]
        assert "422" in responses, f"{path} missing 422"


@pytest.mark.asyncio
async def test_pql_write_routes_declare_error_envelope_in_openapi() -> None:
    """The four PQL write routes expose the envelope contract."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get("/openapi.json")
    schema: dict[str, Any] = resp.json()
    paths = schema.get("paths", {})
    for path in (
        "/api/pql/autoload",
        "/api/pql/write_table",
        "/api/pql/merge",
        "/api/pql/drop_table",
    ):
        assert path in paths, f"missing path: {path}"
        responses = paths[path]["post"]["responses"]
        assert "422" in responses, f"{path} missing 422"
        assert "403" in responses, f"{path} missing 403"


@pytest.mark.asyncio
async def test_error_envelope_schema_carries_code_field() -> None:
    """The shared envelope schema names ``code`` as a required field."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get("/openapi.json")
    schema: dict[str, Any] = resp.json()
    components = schema.get("components", {}).get("schemas", {})
    # Pydantic-derived schema name follows the class name.
    assert "ErrorEnvelope" in components, "ErrorEnvelope must be exported"
    envelope = components["ErrorEnvelope"]
    required = envelope.get("required", [])
    assert "code" in required
    assert "status" in required
    assert "detail" in required
