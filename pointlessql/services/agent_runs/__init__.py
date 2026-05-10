"""Agent-run lifecycle services — registry + events.

The registry routes own ORM persistence; this package holds the
side-effects layered on top — a CloudEvents emitter that fires on
lifecycle transitions so external subscribers
(``hermes-plugin-pointlessql``, Paperclip, an ops dashboard) learn
about runs without polling ``GET /api/agent-runs``.

Webhook destination management is intentionally minimal: a single
URL + optional HMAC secret pulled from
:class:`pointlessql.config.AgentRunsSettings`.  Richer
per-destination subscription would belong on top of this layer.
"""

from __future__ import annotations

from pointlessql.services.agent_runs.events import (
    AGENT_RUN_EVENT_TYPES,
    EVENT_TYPE_COMPLETED,
    EVENT_TYPE_FAILED,
    EVENT_TYPE_STARTED,
    EVENT_TYPE_TOOL_CALL,
    build_agent_run_cloudevent,
    emit_agent_run_event,
    event_type_for_status,
)
from pointlessql.services.agent_runs.operations import (
    OperationRecorder,
    operation_context,
    record_operation,
)

__all__ = [
    "AGENT_RUN_EVENT_TYPES",
    "EVENT_TYPE_COMPLETED",
    "EVENT_TYPE_FAILED",
    "EVENT_TYPE_STARTED",
    "EVENT_TYPE_TOOL_CALL",
    "OperationRecorder",
    "build_agent_run_cloudevent",
    "emit_agent_run_event",
    "event_type_for_status",
    "operation_context",
    "record_operation",
]
