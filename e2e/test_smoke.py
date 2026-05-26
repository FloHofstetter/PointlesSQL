"""Smoke test — verifies the e2e fixture stack boots.

If this test passes we know:

* uvicorn boots against the tempfile DB with the production lifespan.
* ``alembic upgrade head`` succeeds.
* CSRF + form-encoded ``/auth/login`` flow works end-to-end.
* Headless Chromium can navigate to the live server.
* The seeded admin user is authenticated (no redirect to ``/auth/login``).

The richer multi-tab co-edit scenario lives in
``test_notebook_coedit_multi_tab.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.e2e


def test_healthz_responds_via_live_server(playwright_context: Any, live_server_url: str) -> None:
    """Headless Chromium hits ``/healthz`` and gets the JSON envelope."""
    page = playwright_context.new_page()
    try:
        response = page.goto(f"{live_server_url}/healthz", wait_until="load")
        assert response is not None
        assert response.status == 200, f"expected 200 from /healthz, got {response.status}"
        body = response.text()
        assert "ok" in body.lower() or "status" in body.lower()
    finally:
        page.close()


def test_homepage_renders_for_authenticated_admin(
    playwright_context: Any, live_server_url: str
) -> None:
    """Logged-in admin lands somewhere other than the login form.

    Avoid ``networkidle`` — the home page keeps live WebSocket
    notification + presence connections open, so ``networkidle``
    never fires.  ``domcontentloaded`` plus a URL check is enough
    to assert the auth cookies are accepted.
    """
    page = playwright_context.new_page()
    try:
        page.goto(live_server_url, wait_until="domcontentloaded")
        assert "/auth/login" not in page.url, (
            f"admin landed on the login page despite auth cookies: {page.url}"
        )
    finally:
        page.close()
