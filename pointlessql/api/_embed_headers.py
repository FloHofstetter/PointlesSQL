"""Make a public-embed response framable from any origin.

The public, token-gated share/embed pages (saved views, BI dashboards,
semantic-search widgets, shared notebooks) are meant to be iframed into
third-party sites.  The global ``X-Frame-Options: DENY`` added by
:mod:`pointlessql.api.security_headers_middleware` would block that, so an
embed route declares a permissive ``frame-ancestors`` CSP instead — the
middleware skips ``X-Frame-Options`` whenever the response already carries
a ``frame-ancestors`` directive, so the two never conflict.
"""

from __future__ import annotations

from starlette.responses import Response


def allow_framing[ResponseT: Response](response: ResponseT) -> ResponseT:
    """Mark *response* as embeddable from any origin.

    Typed as an identity transform so a route returning an ``HTMLResponse``
    (or any other concrete response) keeps that static type through the call.

    Args:
        response: The embed/share page response.

    Returns:
        The same response, with a permissive ``frame-ancestors`` CSP and no
        conflicting ``X-Frame-Options`` (the middleware skips it).
    """
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    # Defensive: if anything upstream already stamped X-Frame-Options, drop
    # it so it cannot override the frame-ancestors policy.  Starlette's
    # MutableHeaders has no ``pop``, so delete only when present.
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response


def allow_framing_same_origin[ResponseT: Response](response: ResponseT) -> ResponseT:
    """Mark *response* as embeddable only from the same origin.

    Private in-app artefacts — the executed-notebook HTML the job-detail
    "Output artifacts" card iframes, the run-compare page's twin iframes,
    and the dashboard output iframe — are framed by our own pages but must
    not be embeddable by third-party sites. The global
    ``X-Frame-Options: DENY`` blocks framing outright, including the
    same-origin case, so declare an enforced ``frame-ancestors 'self'``
    instead: the middleware then skips ``X-Frame-Options`` and the browser
    permits the same-origin embed while still denying cross-origin ones.

    Args:
        response: The private same-origin artefact response.

    Returns:
        The same response, scoped to same-origin framing with no
        conflicting ``X-Frame-Options``.
    """
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response
