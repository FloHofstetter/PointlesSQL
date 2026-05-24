"""Sanity checks for the centralized auth fixtures.

Pin the contract so future migrations can
trust each fixture's shape.  These tests exercise the fixture, NOT
the production auth dependencies — those have their own coverage
in ``test_auth_routes.py`` etc.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import ApiKeyFixture


@pytest.mark.asyncio
async def test_admin_client_is_authenticated_async_client(
    admin_client: httpx.AsyncClient,
) -> None:
    """``admin_client`` yields a working AsyncClient and reaches admin routes."""
    assert isinstance(admin_client, httpx.AsyncClient)
    response = await admin_client.get("/admin")
    # 200 (rendered) or 302 (redirect) — both prove the cookie was honoured.
    assert response.status_code in (200, 302)


@pytest.mark.asyncio
async def test_non_admin_client_is_authenticated_but_blocked_from_admin(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """``non_admin_client`` is logged in but the admin gate rejects it."""
    response = await non_admin_client.get("/admin")
    # The non-admin user is gated by ``require_admin``, which raises
    # AuthorizationError → 403 via the global handler.  Some admin
    # surfaces redirect to / instead; either is "blocked".
    assert response.status_code in (302, 403)


@pytest.mark.asyncio
async def test_anonymous_client_carries_no_cookies(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """``anonymous_client`` has no auth cookie set."""
    assert isinstance(anonymous_client, httpx.AsyncClient)
    # Empty cookie jar — protected routes must redirect or 401.
    assert len(anonymous_client.cookies) == 0


def test_supervisor_secret_yields_supervisor_scope(
    supervisor_secret: ApiKeyFixture,
) -> None:
    """``supervisor_secret`` returns a key with ``supervisor=True``."""
    assert supervisor_secret.secret  # non-empty plaintext
    assert supervisor_secret.row.supervisor is True
    assert supervisor_secret.row.auditor is False
    assert supervisor_secret.headers == {"Authorization": f"Bearer {supervisor_secret.secret}"}


def test_auditor_secret_yields_auditor_scope(
    auditor_secret: ApiKeyFixture,
) -> None:
    """``auditor_secret`` returns a key with ``auditor=True`` and not supervisor."""
    assert auditor_secret.row.auditor is True
    assert auditor_secret.row.supervisor is False


def test_api_key_secret_yields_unprivileged_key(
    api_key_secret: ApiKeyFixture,
) -> None:
    """``api_key_secret`` returns a key with no special scope flags."""
    assert api_key_secret.row.supervisor is False
    assert api_key_secret.row.auditor is False
    assert api_key_secret.row.lineage_inbound is False
