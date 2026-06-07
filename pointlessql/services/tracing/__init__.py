"""Request/operation correlation surface (G4).

Wraps the existing :data:`pointlessql.config.correlation_id_var`
ContextVar in a stable importable surface so downstream callers
(``pql/_write.py``, audit-emit helpers, scheduler executors) don't
need to know about the underlying logging-config module.
"""

from __future__ import annotations

from pointlessql.services.tracing._context import (
    current_correlation_id,
    current_request_id,
    set_correlation_id,
)
from pointlessql.services.tracing._otel import (
    init_tracing,
    is_enabled,
    traced,
)

__all__ = [
    "current_correlation_id",
    "current_request_id",
    "init_tracing",
    "is_enabled",
    "set_correlation_id",
    "traced",
]
