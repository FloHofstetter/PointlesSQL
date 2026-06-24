"""Public embeds opt into cross-origin framing without losing global hardening.

The security-headers middleware stamps ``X-Frame-Options: DENY`` on every
response so the app cannot be clickjacked.  The token-gated public embeds
(saved views, BI dashboards, semantic-search widgets, shared notebooks) are
the deliberate exception: they are meant to be iframed into third-party
sites.  ``allow_framing`` declares a permissive ``frame-ancestors`` CSP on
those responses, and the middleware skips ``X-Frame-Options`` whenever it
sees that directive — so the two policies never conflict, and only the
opted-in routes are framable.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.responses import Response

from pointlessql.api._embed_headers import allow_framing
from pointlessql.api.security_headers_middleware import security_headers_middleware


def _request(scheme: str = "http") -> Request:
    """Build a minimal GET request whose URL carries *scheme*."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": scheme,
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
        }
    )


async def _plain(_: Request) -> Response:
    """Downstream handler returning a default (non-embed) response."""
    return Response("ok")


async def _framable(_: Request) -> Response:
    """Downstream handler returning an embed response."""
    return allow_framing(Response("ok"))


def test_allow_framing_sets_csp_and_drops_xfo() -> None:
    """``allow_framing`` declares ``frame-ancestors *`` and clears any XFO."""
    response = Response("body")
    response.headers["X-Frame-Options"] = "DENY"

    out = allow_framing(response)

    assert out.headers["content-security-policy"] == "frame-ancestors *"
    assert "x-frame-options" not in {k.lower() for k in out.headers}


@pytest.mark.asyncio
async def test_plain_response_gets_frame_deny() -> None:
    """A normal response is stamped ``X-Frame-Options: DENY`` (clickjacking)."""
    out = await security_headers_middleware(_request(), _plain)

    assert out.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_framable_response_keeps_only_frame_ancestors() -> None:
    """An embed response keeps its CSP and is not given a conflicting XFO."""
    out = await security_headers_middleware(_request(), _framable)

    assert out.headers["content-security-policy"] == "frame-ancestors *"
    assert "x-frame-options" not in {k.lower() for k in out.headers}


@pytest.mark.asyncio
async def test_hsts_only_on_https() -> None:
    """HSTS is added for HTTPS requests only, so HTTP dev is unaffected."""
    over_http = await security_headers_middleware(_request("http"), _plain)
    over_https = await security_headers_middleware(_request("https"), _plain)

    assert "strict-transport-security" not in {k.lower() for k in over_http.headers}
    assert "strict-transport-security" in {k.lower() for k in over_https.headers}
