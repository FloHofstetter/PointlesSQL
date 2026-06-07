"""OpenTelemetry tracing bridge — opt-in, default off, zero core deps.

When observability is disabled (the default) this module imports no
OpenTelemetry package and every helper is a no-op, so a clean
``uv run pointlessql`` carries no tracing dependency and needs no
collector.  When enabled via :class:`ObservabilitySettings`, it lazily
imports the OTel SDK, wires an OTLP span exporter, and exposes a
:func:`traced` context manager that tags each span with the request and
correlation IDs already threaded through the logging context — so traces
and structured logs share the same identifiers.

The bridge is deliberately defensive: a missing OpenTelemetry install or a
misconfigured endpoint degrades to the no-op path with a warning rather
than breaking request handling.  Wire :func:`init_tracing` into the app
lifespan only when ``settings.observability.enabled`` is true.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from pointlessql.services.tracing._context import (
    current_correlation_id,
    current_request_id,
)

if TYPE_CHECKING:
    from pointlessql.config._settings._infra import ObservabilitySettings

logger = logging.getLogger(__name__)

# Module-level state.  ``_tracer`` is the live OTel tracer once init
# succeeds; ``None`` means tracing is off (default) and every span helper
# short-circuits.  Held at module scope so the middleware / service layer
# can call :func:`traced` without threading a handle through every call.
_tracer: Any = None
_enabled: bool = False


def init_tracing(settings: ObservabilitySettings) -> bool:
    """Initialise OTLP tracing from *settings*; return whether it is active.

    Idempotent and total: returns ``False`` (leaving the no-op path in
    place) when observability is disabled, when the OpenTelemetry SDK is
    not installed, or when exporter setup raises.  Only returns ``True``
    after a tracer is successfully installed.

    Args:
        settings: The resolved observability settings
            (``get_settings().observability``).

    Returns:
        ``True`` if a live tracer is now installed, ``False`` otherwise.
    """
    global _tracer, _enabled
    if not settings.enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.warning(
            "observability.enabled but OpenTelemetry is not installed; "
            "install the 'observability' optional dependency group. Tracing stays off."
        )
        return False
    try:
        resource = Resource.create({"service.name": settings.service_name})
        provider = TracerProvider(
            resource=resource,
            sampler=TraceIdRatioBased(max(0.0, min(1.0, settings.sample_ratio))),
        )
        exporter = OTLPSpanExporter(endpoint=settings.tracing_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("pointlessql")
        _enabled = True
        logger.info("OpenTelemetry tracing initialised (endpoint=%s)", settings.tracing_endpoint)
        return True
    except Exception:  # noqa: BLE001 — tracing setup must never break startup
        logger.warning(
            "OpenTelemetry tracing setup failed; continuing without tracing", exc_info=True
        )
        _tracer = None
        _enabled = False
        return False


def is_enabled() -> bool:
    """Return whether a live tracer is installed."""
    return _enabled and _tracer is not None


@contextmanager
def traced(name: str, **attributes: Any) -> Iterator[Any]:
    """Open a span named *name*, or a no-op when tracing is off.

    Tags the span with the current request and correlation IDs (so the
    trace lines up with the structured logs emitted under the same
    request) plus any caller-supplied *attributes*.  When tracing is
    disabled this is a near-free no-op that simply yields ``None``.

    Args:
        name: The span name (operation label).
        **attributes: Extra string/number/bool span attributes.

    Yields:
        The active span, or ``None`` when tracing is off.
    """
    if not is_enabled():
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        try:
            request_id = current_request_id()
            if request_id:
                span.set_attribute("pointlessql.request_id", request_id)
            correlation_id = current_correlation_id()
            if correlation_id:
                span.set_attribute("pointlessql.correlation_id", correlation_id)
            for key, value in attributes.items():
                span.set_attribute(key, value)
        except Exception:  # noqa: BLE001 — attribute tagging must not break the span body
            logger.debug("failed to tag span attributes", exc_info=True)
        yield span
