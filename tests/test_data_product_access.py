"""Tests for the self-service data-product access-request flow.

Covers filing a request (only when the caller lacks SELECT), the
steward/admin approve path issuing a real UC grant through the client,
denial, the ownership gate on decisions, and the consumer status
endpoint.  The UC client is driven with ``AsyncMock`` so no soyuz
server is needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_product_access_request import (
    DataProductAccessRequest,
)

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    load_contract(yaml_path, factory=app.state.session_factory)


@pytest.fixture
def uc_mock() -> Iterator[MagicMock]:
    """Swap app.state.uc_client for a controllable async mock + restore.

    Default: the caller holds no privileges (empty effective list) and
    grants succeed.
    """
    original = app.state.uc_client
    fake = MagicMock()
    fake.get_effective_permissions = AsyncMock(return_value=[])
    fake.update_permissions = AsyncMock(return_value=[])
    app.state.uc_client = fake
    try:
        yield fake
    finally:
        app.state.uc_client = original


@pytest.mark.asyncio
async def test_request_access_creates_pending(
    tmp_path: Path, non_admin_client: httpx.AsyncClient, uc_mock: MagicMock
) -> None:
    """A consumer without SELECT can file a request; status reflects it."""
    _seed_product(tmp_path)
    res = await non_admin_client.post(
        "/api/data-products/main/sales_gold/access-requests",
        json={"note": "Need it for the Q3 report"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending"

    status = (
        await non_admin_client.get("/api/data-products/main/sales_gold/access-requests/status")
    ).json()
    assert status["can_select"] is False
    assert status["has_pending"] is True


@pytest.mark.asyncio
async def test_request_access_when_already_has_access_400(
    tmp_path: Path, admin_client: httpx.AsyncClient, uc_mock: MagicMock
) -> None:
    """An admin already has access, so filing a request is rejected."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/access-requests", json={}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_approve_grants_select_and_transitions(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
    uc_mock: MagicMock,
) -> None:
    """Approval issues a UC SELECT grant and marks the request approved."""
    _seed_product(tmp_path)
    req = await non_admin_client.post(
        "/api/data-products/main/sales_gold/access-requests", json={}
    )
    req_id = req.json()["id"]

    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/access-requests/{req_id}/approve",
        json={},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert "main.sales_gold.orders" in body["granted"]

    # the grant went through the client with SELECT for the requester
    uc_mock.update_permissions.assert_awaited()
    args = uc_mock.update_permissions.await_args
    assert args.args[0] == "table"
    assert args.args[1] == "main.sales_gold.orders"
    assert args.args[2] == [
        {"principal": "nonadmin@test.com", "add": ["SELECT"], "remove": []}
    ]

    with app.state.session_factory() as session:
        row = session.scalar(
            select(DataProductAccessRequest).where(DataProductAccessRequest.id == req_id)
        )
        assert row.status == "approved"


@pytest.mark.asyncio
async def test_deny_transitions_without_grant(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
    uc_mock: MagicMock,
) -> None:
    """Denial records the decision and issues no grant."""
    _seed_product(tmp_path)
    req_id = (
        await non_admin_client.post(
            "/api/data-products/main/sales_gold/access-requests", json={}
        )
    ).json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/access-requests/{req_id}/deny",
        json={"reason": "Not this quarter"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "denied"
    uc_mock.update_permissions.assert_not_awaited()


@pytest.mark.asyncio
async def test_decision_requires_steward_or_admin(
    tmp_path: Path, non_admin_client: httpx.AsyncClient, uc_mock: MagicMock
) -> None:
    """A non-steward consumer cannot approve a request (even their own)."""
    _seed_product(tmp_path)
    req_id = (
        await non_admin_client.post(
            "/api/data-products/main/sales_gold/access-requests", json={}
        )
    ).json()["id"]
    res = await non_admin_client.post(
        f"/api/data-products/main/sales_gold/access-requests/{req_id}/approve",
        json={},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_steward_sees_pending_in_list(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
    uc_mock: MagicMock,
) -> None:
    """The admin/steward list surfaces pending requests with the requester."""
    _seed_product(tmp_path)
    await non_admin_client.post(
        "/api/data-products/main/sales_gold/access-requests", json={"note": "please"}
    )
    listing = (
        await admin_client.get("/api/data-products/main/sales_gold/access-requests")
    ).json()
    assert len(listing["requests"]) == 1
    assert listing["requests"][0]["requester"]["email"] == "nonadmin@test.com"
    assert listing["requests"][0]["request_note"] == "please"
