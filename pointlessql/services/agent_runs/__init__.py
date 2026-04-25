"""Agent-run lifecycle services — Sprint 13 (registry + events).

The Sprint-13.2 registry routes own ORM persistence; this package
holds the side-effects layered on top — Sprint 13.3 ships the
CloudEvents emitter that fires on lifecycle transitions so external
subscribers (the future ``hermes-plugin-pointlessql``,
Paperclip, an ops dashboard) learn about runs without polling
``GET /api/agent-runs``.

Webhook destination management stays minimal in 13.3: a single
URL + optional HMAC secret pulled from
:class:`pointlessql.settings.AgentRunsSettings`.  The richer
per-destination subscription model lands with the Sprint 13.4
control-room work.
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
