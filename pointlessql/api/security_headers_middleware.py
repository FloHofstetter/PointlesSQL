"""Security response-header middleware.

Adds the standard browser-hardening headers to every response and a
**report-only** Content-Security-Policy.  Report-only is deliberate: the UI
leans on Alpine.js inline directives, HTMX, and CodeMirror, which a strict
enforced CSP would break.  Shipping the policy in report-only mode collects
real violations (via the ``/api/csp-report`` collector) so the policy can be
tightened against evidence before it is ever switched to enforcing.

The policy already names the only third-party origin the UI loads from
(``https://cdn.jsdelivr.net``) so the collector reflects genuine
violations rather than expected CDN loads.  The remaining path to
enforcement is dropping ``'unsafe-inline'`` / ``'unsafe-eval'`` (nonce or
hash the inline Alpine/HTMX directives) — that is what the report-only
window is there to de-risk.

The non-CSP headers are unconditional and safe to enforce immediately:

* ``X-Content-Type-Options: nosniff`` — no MIME sniffing.
* ``X-Frame-Options: DENY`` — no framing (clickjacking).
* ``Referrer-Policy: strict-origin-when-cross-origin`` — no path/query leak
  to third parties.
* ``Strict-Transport-Security`` — only when the request arrived over HTTPS,
  so local HTTP development is unaffected.

Registered just inside the latency middleware so the headers are applied to
the final response on the way out.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

CSP_REPORT_PATH = "/api/csp-report"

# Report-only policy.  Tighten against collected reports before enforcing.
# ``'unsafe-inline'`` / ``'unsafe-eval'`` are present only so the report-only
# policy does not drown the collector in noise from the existing Alpine/HTMX
# inline handlers; the goal is to remove them as the templates are migrated.
# jsdelivr is the only third-party origin the UI loads from (Bootstrap +
# bootstrap-icons CSS/woff, HTMX, Alpine, Chart.js). Naming it here keeps
# the report-only collector from drowning in CDN false positives, which is
# the prerequisite for flipping the policy to enforcing. All fetch/SSE/WS
# targets are same-origin, so connect-src stays 'self'.
_JSDELIVR = "https://cdn.jsdelivr.net"
_CSP_REPORT_ONLY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    f"style-src 'self' 'unsafe-inline' {_JSDELIVR}; "
    f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {_JSDELIVR}; "
    f"font-src 'self' {_JSDELIVR}; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    f"report-uri {CSP_REPORT_PATH}"
)

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy-Report-Only": _CSP_REPORT_ONLY,
}


async def security_headers_middleware(request: Request, call_next: Any) -> Response:
    """Attach hardening headers (and a report-only CSP) to every response.

    Existing headers are never overwritten, so a route that sets its own
    stricter policy wins.  HSTS is added only for HTTPS requests so plain
    HTTP local development is unaffected.

    Args:
        request: The incoming request.
        call_next: The downstream handler.

    Returns:
        The downstream response with the security headers added.
    """
    response = await call_next(request)
    for name, value in _STATIC_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response
