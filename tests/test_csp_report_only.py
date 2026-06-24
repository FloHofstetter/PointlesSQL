"""The report-only CSP names the real CDN origin so it can flip to enforce.

Omitting jsdelivr meant every CDN script/style/font load reported as a
violation, drowning the collector and blocking the move to an enforced
policy.  This pins that the report-only header allows jsdelivr in the
script/style/font directives while keeping connect-src same-origin.
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_report_only_csp_allows_jsdelivr(anonymous_client: httpx.AsyncClient) -> None:
    """script/style/font allow jsdelivr; connect/img stay locked down."""
    res = await anonymous_client.get("/auth/login")
    csp = res.headers.get("content-security-policy-report-only", "")
    assert "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net" in csp
    assert "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net" in csp
    assert "font-src 'self' https://cdn.jsdelivr.net" in csp
    assert "connect-src 'self';" in csp
    assert "img-src 'self' data:;" in csp
    # Still report-only — this change does not flip enforcement.
    header_names = {k.lower() for k in res.headers}
    assert "content-security-policy-report-only" in header_names
    assert "content-security-policy" not in header_names
