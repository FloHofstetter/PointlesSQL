"""Template + HTMX + content-negotiation request dependencies.

The shared :class:`Jinja2Templates` accessor, the HTMX header probes
(``HX-Request`` / ``HX-Boosted``), JSON-vs-HTML content negotiation,
and the :func:`render_page_with_fallback` helper that surfaces UC
outages as an in-page banner instead of a 500.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from pointlessql.exceptions import CatalogUnavailableError


def get_templates(request: Request) -> Jinja2Templates:
    """Return the shared :class:`Jinja2Templates` instance from app state.

    The template factory is configured once at app startup (filters,
    autoescape, search path) and stashed on
    ``request.app.state.templates``.  Routes used to redefine a private
    ``_templates`` helper file-by-file — it is promoted here so
    HTML routes share one helper and bug-fixes to the rendering shim
    only land in one place.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The shared :class:`Jinja2Templates`.
    """
    return request.app.state.templates


def is_htmx_request(request: Request) -> bool:
    """Return True when the request carries the ``HX-Request`` marker.

    HTMX sets ``HX-Request: true`` on every fetch it issues (inline
    edits, fragment swaps, boosted navigations).  Use this when the
    distinction between "any HTMX call" and "full-page request"
    matters, regardless of boost mode.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff the ``HX-Request`` header equals ``"true"``.
    """
    return request.headers.get("HX-Request") == "true"


def is_htmx_boosted(request: Request) -> bool:
    """Return True when the request is an HTMX boosted navigation.

    Boosted nav (``hx-boost``) asks HTMX to behave like a full-page
    swap of ``#main-content``.  The client still expects a complete
    HTML shell with the target block — partial-only renderers must
    skip this branch.  Implies :func:`is_htmx_request`.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff the ``HX-Boosted`` header equals ``"true"``.
    """
    return request.headers.get("HX-Boosted") == "true"


def is_htmx_partial(request: Request) -> bool:
    """Return True when the request is an HTMX fragment (non-boosted) call.

    The common shape for inline edits, Load-More buttons, and toast
    targets.  Boosted navigations are *not* partials — they want the
    full HTML shell.  Three call sites had this same expression
    spelled out by hand centralised it.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff ``HX-Request`` is set and ``HX-Boosted`` is not.
    """
    return is_htmx_request(request) and not is_htmx_boosted(request)


def wants_json(request: Request) -> bool:
    """Return True when the caller prefers a JSON / problem+json body.

    ``/api/...`` paths always return JSON.  For other paths, honour
    an explicit ``Accept: application/json`` (or the RFC-9457 media
    type ``application/problem+json``) that does not also include
    ``text/html`` — browsers send ``text/html`` first, so they land
    on the HTML shell.  Promoted from ``error_handlers._wants_json``
    so non-error routes can negotiate the same way.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` when JSON / problem+json is preferred, ``False`` for
        an HTML fallback.
    """
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    if not accept:
        return False
    lower = accept.lower()
    has_json = "application/json" in lower or "application/problem+json" in lower
    return has_json and "text/html" not in lower


async def render_page_with_fallback(
    request: Request,
    template_name: str,
    fetch_fn: Callable[[], Awaitable[Any]],
    *,
    context_key: str,
    extra_context: dict[str, Any] | None = None,
) -> Response:
    """Render *template_name* with fetched data; surface UC outages as a banner.

    extracts the
    ``try/except CatalogUnavailableError`` + ``render template with
    error banner`` pattern repeated across federation_routes,
    catalog_html_routes, home_routes, and memory_routes.  Routes
    delegate the fetch + error handling to one place; their bodies
    shrink to ``return await render_page_with_fallback(...)``.

    Args:
        request: Incoming FastAPI request — needed for
            :func:`get_templates` and the template response builder.
        template_name: Jinja template path (e.g.
            ``"pages/connections.html"``).
        fetch_fn: Async no-arg callable that returns the data to
            inject under *context_key*.  Typical pattern is a bound
            method reference: ``client.list_connections``.
        context_key: Template variable name for the fetched data.
            Pages that do not expect a "found object" key (e.g. the
            error-banner-only page) still get an empty list under
            this key on UC outage.
        extra_context: Additional template variables merged into
            the rendered context.  ``error`` is reserved — the
            helper always injects it (``None`` on success,
            ``exc.detail`` on UC failure).

    Returns:
        :class:`Response` carrying the rendered template — populated
        data on success, empty + ``error`` banner on UC outage.
    """
    items: Any = []
    error: str | None = None
    try:
        items = await fetch_fn()
    except CatalogUnavailableError as exc:
        error = exc.detail
    context: dict[str, Any] = {context_key: items, "error": error}
    if extra_context:
        context.update(extra_context)
    return get_templates(request).TemplateResponse(request, template_name, context)
