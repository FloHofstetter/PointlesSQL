"""Pure JSON-side coercers and the public ORM serializer.

``serialize_agent_run`` is the only public name in this module —
it owns the dict shape that ``/runs`` and ``/runs/{id}`` consume in
their template context, so the same serializer powers HTML and JSON
responses without a second mapping.  The three coercers are
package-internal validators for the registry / finish endpoint
bodies.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.models.agent_runs import AgentRun


def serialize_agent_run(row: AgentRun) -> dict[str, Any]:
    """Render an :class:`AgentRun` ORM row into a JSON-safe dict.

    The shape matches what ``/runs`` and ``/runs/{id}`` expect in
    their template context, so the same serializer powers the HTML
    and JSON responses without a second mapping.

    Args:
        row: The ORM row to serialize.

    Returns:
        Plain dict with ISO-formatted timestamps and a decoded
        ``tables_touched`` list.
    """
    tables: list[str] = []
    if row.tables_touched:
        try:
            parsed: Any = json.loads(row.tables_touched)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            tables = [
                str(item)  # pyright: ignore[reportUnknownArgumentType]
                for item in parsed  # pyright: ignore[reportUnknownVariableType]
            ]
    runtime_versions: dict[str, Any] = {}
    if row.runtime_versions:
        try:
            decoded: Any = json.loads(row.runtime_versions)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            runtime_versions = decoded  # pyright: ignore[reportUnknownVariableType]
    cost_gate_trigger: dict[str, Any] | None = None
    if row.cost_gate_trigger:
        try:
            decoded_trigger: Any = json.loads(row.cost_gate_trigger)
        except json.JSONDecodeError:
            decoded_trigger = None
        if isinstance(decoded_trigger, dict):
            cost_gate_trigger = decoded_trigger  # pyright: ignore[reportUnknownVariableType]
    return {
        "id": row.id,
        "principal": row.principal,
        "agent_id": row.agent_id,
        "notebook_path": row.notebook_path,
        "source_snapshot_sha": row.source_snapshot_sha,
        "status": row.status,
        "cost_est": float(row.cost_est) if row.cost_est is not None else None,
        "tables_touched": tables,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "exit_code": row.exit_code,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "denied_reason": row.denied_reason,
        "runtime_versions": runtime_versions,
        "cost_gate_trigger": cost_gate_trigger,
        "anomaly_severity": row.anomaly_severity,
        "anomaly_metric": row.anomaly_metric,
    }


def coerce_tables_touched(value: Any) -> str | None:
    """Normalize the ``tables_touched`` payload into a JSON-encoded list.

    Accepts a ``list[str]`` from JSON bodies; rejects anything else
    so a malformed payload cannot round-trip through the store.

    Args:
        value: Raw field value from the request body.

    Returns:
        JSON-encoded array text, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is neither ``None`` nor a list
            of strings.
    """
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, str)
        for item in value  # pyright: ignore[reportUnknownVariableType]
    ):
        raise ValidationError("tables_touched must be a list of strings")
    return json.dumps(value)


def coerce_cost_gate_trigger(value: Any) -> str | None:
    """Validate and JSON-encode the ``cost_gate_trigger`` snapshot.

    The runtime forwards the dict the cost gate emitted on
    ``/api/sql/explain`` (see ``sql_routes.api_sql_explain``) so the
    reviewer can see the EXPLAIN plan, threshold, and estimated cost
    that produced the verdict without re-running the query.

    Args:
        value: Raw field value from the request body.

    Returns:
        JSON-encoded mapping text, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is neither ``None`` nor a
            JSON-serializable mapping.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError("cost_gate_trigger must be a JSON object")
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("cost_gate_trigger must be JSON-serializable") from exc


def coerce_cost_est(value: Any) -> Decimal | None:
    """Parse ``cost_est`` into a :class:`Decimal`, rejecting bad shapes.

    Args:
        value: Raw field value from the request body.

    Returns:
        The parsed :class:`Decimal`, or ``None`` when unset.

    Raises:
        ValidationError: If ``value`` is not null, numeric, or a
            numeric string.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError("cost_est must be numeric") from exc
