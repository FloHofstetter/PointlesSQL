"""Phase 91 — route smoke test for ``GET .../tables/{t}/stats``.

The pandas reduction is exercised in
``test_column_stats_service.py``; this file only verifies the
auth gate, the path-parameter binding, and the cache-hit
behaviour of the route layer.  The underlying
``compute_table_stats`` is monkeypatched so we don't need a real
Delta table on disk.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app


@pytest.fixture(autouse=True)
def _patch_compute(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace the pandas reduction with a counter-bumping stub."""
    counter = {"hits": 0}

    def fake_compute(settings: Any, principal: str, full_name: Any) -> dict[str, Any]:
        counter["hits"] += 1
        return {
            "row_count": 1234,
            "columns": [
                {
                    "name": "id",
                    "dtype": "int64",
                    "nullability_pct": 0.0,
                    "n_distinct": 1234,
                    "min": 1,
                    "max": 1234,
                }
            ],
        }

    monkeypatch.setattr(
        "pointlessql.services.column_stats._compute.compute_table_stats",
        fake_compute,
    )
    # The route imports lazily — patch the binding site too.
    monkeypatch.setattr(
        "pointlessql.services.column_stats.compute_table_stats",
        fake_compute,
    )
    return counter


@pytest.fixture(autouse=True)
def _patch_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip UC permission lookup — the route uses SELECT-gate."""
    from pointlessql.services.unitycatalog import UnityCatalogClient

    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        app.state.uc_client,
        "get_effective_permissions",
        AsyncMock(return_value=[]),
    )

    def fake_check(*args: Any, **kwargs: Any) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "pointlessql.api.catalog_routes.check_privilege_from_effective",
        fake_check,
    )


async def test_stats_route_returns_payload(
    admin_client: httpx.AsyncClient,
    _patch_compute: dict[str, int],
) -> None:
    """Admin GETs the stats payload as JSON."""
    response = await admin_client.get(
        "/api/catalogs/main/schemas/sales/tables/orders/stats"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 1234
    assert body["columns"][0]["name"] == "id"
    assert response.headers["cache-control"] == "no-store"
    assert _patch_compute["hits"] == 1


async def test_stats_route_anonymous_rejected(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Unauthenticated requests get rejected before the compute runs."""
    response = await anonymous_client.get(
        "/api/catalogs/main/schemas/sales/tables/orders/stats"
    )
    assert response.status_code in (401, 403)


async def test_stats_route_path_parameters_propagated(
    admin_client: httpx.AsyncClient,
) -> None:
    """Route binds catalog/schema/table from the URL path."""
    seen: dict[str, str] = {}

    def fake_compute(settings: Any, principal: str, full_name: Any) -> dict[str, Any]:
        seen["fqn"] = str(full_name)
        return {"row_count": 0, "columns": []}

    # Re-patch the symbol the route imported.
    from pointlessql.services import column_stats as cs

    original = cs.compute_table_stats
    cs.compute_table_stats = fake_compute  # type: ignore[assignment]
    try:
        response = await admin_client.get(
            "/api/catalogs/foo/schemas/bar/tables/baz/stats"
        )
        assert response.status_code == 200
        assert seen["fqn"] == "foo.bar.baz"
    finally:
        cs.compute_table_stats = original  # type: ignore[assignment]
