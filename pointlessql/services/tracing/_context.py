"""ContextVar surface for request + correlation IDs.

The middleware (:mod:`pointlessql.api.middleware`) sets the
underlying ContextVars on each request entry; downstream layers read
them through this stable module so we can swap the substrate without
ripping out call sites.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from pointlessql.config import correlation_id_var, request_id_var


def current_correlation_id() -> str | None:
    """Return the active correlation-id, or ``None`` outside a request."""
    return correlation_id_var.get()


def current_request_id() -> str | None:
    """Return the active request-id, or ``None`` outside a request."""
    return request_id_var.get()


@contextmanager
def set_correlation_id(value: str | None) -> Iterator[None]:
    """Temporarily override the correlation-id (testing/background jobs).

    Resets to the prior value on exit so cross-test isolation holds
    even when scheduler tasks share a single event loop.
    """
    token = correlation_id_var.set(value)
    try:
        yield
    finally:
        correlation_id_var.reset(token)
