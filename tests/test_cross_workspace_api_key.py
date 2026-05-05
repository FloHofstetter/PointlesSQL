"""Sprint 28.5 — server-side enforcement of api_key.workspace_id pin.

A Bearer-authed call cannot escape the workspace its api_key is
pinned to:

* No header → resolver picks the api_key's pinned workspace_id
  (silent path).
* Mismatched ``X-Workspace`` header → 403, audit-logged
  ``workspace.context_mismatch``.
* Matching ``X-Workspace`` header → request flows through unchanged.

Together with the plugin-side test
(``hermes-plugin-pointlessql/tests/test_workspace_header.py``) this
forms the round-trip contract for Sprint 28.5.
"""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import ApiKey, AuditLog
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import workspaces as workspaces_service


def _factory():
    return app.state.session_factory


@pytest.fixture
def pinned_api_key():
    """Mint an api_key pinned to a fresh workspace, return (token, ws_id)."""
    ws = workspaces_service.create_workspace(_factory(), slug="ws-cross-pin", name="Cross-Pin")
    factory = _factory()
    _, token = api_keys_service.create_api_key(
        factory,
        name="cross-workspace-test-key",
        supervisor=False,
        auditor=True,
        workspace_id=ws.id,
    )
    api_keys_service.invalidate_cache()
    yield token, ws.id
    with factory() as session:
        session.execute(ApiKey.__table__.delete().where(ApiKey.name == "cross-workspace-test-key"))
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.mark.asyncio
async def test_no_header_resolves_to_api_key_pin(pinned_api_key: tuple[str, int]) -> None:
    """Without X-Workspace, the resolver picks the api_key's pin."""
    token, _ = pinned_api_key
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/audit/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
    # 200 is the happy path; 403 means the workspace gate fired,
    # which would be a regression.  A 422 / 5xx would be unrelated.
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_mismatched_header_returns_403(pinned_api_key: tuple[str, int]) -> None:
    """A header pointing at the *default* workspace 403s a key pinned elsewhere."""
    token, _ = pinned_api_key
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/audit/summary",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Workspace": "default",
            },
        )
    assert response.status_code == 403
    body = response.json()
    assert body.get("error") == "workspace.context_mismatch"


@pytest.mark.asyncio
async def test_mismatched_header_writes_audit_row(pinned_api_key: tuple[str, int]) -> None:
    """Cross-workspace probe leaves an audit-log breadcrumb."""
    token, ws_id = pinned_api_key
    factory = _factory()
    before = datetime.datetime.now(datetime.UTC)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.get(
            "/api/audit/summary",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Workspace": "default",
            },
        )
    with factory() as session:
        rows = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "workspace.context_mismatch",
                    AuditLog.created_at >= before,
                )
            ).all()
        )
    assert len(rows) >= 1
    detail_text = " ".join(str(row.detail) for row in rows)
    assert "default" in detail_text


@pytest.mark.asyncio
async def test_matching_header_is_accepted(pinned_api_key: tuple[str, int]) -> None:
    """Explicit X-Workspace matching the pin flows through unchanged."""
    token, _ = pinned_api_key
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/audit/summary",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Workspace": "ws-cross-pin",
            },
        )
    assert response.status_code == 200, response.text
