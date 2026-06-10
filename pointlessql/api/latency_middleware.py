"""Per-route HTTP latency middleware.

Times every request end-to-end and records it into the shared Prometheus
registry as ``pointlessql_http_request_duration_seconds``, labelled by the
matched route **template**, method, and status.  This is the per-route leg
of the RED (rate / errors / duration) picture; the rate and error counters
live alongside it in :mod:`pointlessql.services.metrics`.

The middleware is registered outermost (last in ``register_middleware`` so
it runs first on the way in, last on the way out) so the measured latency
includes the time spent in every inner middleware — auth, rate-limit, CSRF,
request-id — not just the route handler.

Label cardinality is bounded on purpose: the route label is always the
templated path Starlette matched (``/api/audit/{id}``), never the concrete
path with IDs or query strings, so a multi-workspace install with millions
of distinct paths cannot blow up the metric's series count.
"""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from pointlessql.services import metrics


def _route_template(request: Request) -> str:
    """Return the matched route template, or ``"unmatched"``.

    Starlette stores the resolved route on ``request.scope["route"]`` once
    routing has run (i.e. after ``call_next``).  Reading its ``path``
    attribute yields the low-cardinality template; a request that matched
    no route (404 before routing) has no route object.
    """
    route: Any = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return "unmatched"


async def latency_middleware(request: Request, call_next: Any) -> Response:
    """Measure and record one request's end-to-end latency.

    Records the observation on both the success and the error path (an
    uncaught handler exception is timed as a ``500`` before being
    re-raised), so the error tail is never silently dropped from the
    latency histogram.

    Args:
        request: The incoming request.
        call_next: The downstream ASGI handler.

    Returns:
        The downstream response, unmodified.

    Raises:
        Exception: Whatever the downstream handler raised, re-raised
            unchanged after the timing observation is recorded.
    """
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start
        metrics.record_http_latency(_route_template(request), request.method, 500, duration)
        raise
    duration = time.perf_counter() - start
    metrics.record_http_latency(
        _route_template(request), request.method, response.status_code, duration
    )
    return response
