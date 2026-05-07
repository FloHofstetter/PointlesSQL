"""HTTP wrapper around the in-process ``pql.training_context()`` capture.

the Hermes plugin is HTTP-only (no PointlesSQL imports);
without an HTTP surface, agents that train models through the plugin
cannot persist the autolog snapshot that
:func:`pointlessql.services.agent_runs.training_context.training_context`
writes inline.  This module bridges the gap with one post-hoc endpoint:
the agent runs ``mlflow.autolog()`` locally, captures the run's
params + metrics dict, and POSTs the pair here so a
``record_operation(op_name="train_model")`` row lands with the same
``training_params_json`` shape the in-process flow produces.

The endpoint is **best-effort**: validation failures raise (so the
agent sees a clear 400), but no MLflow connectivity is required —
``mlflow_run_id`` is opaque metadata stamped into ``params_json`` for
the cross-link, never re-read by this route.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.exceptions import ValidationError
from pointlessql.identifiers import RunId
from pointlessql.services.agent_runs.operations import (
    VALID_OP_NAMES,
    record_operation,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pql-training"])


def _coerce_iso(value: Any, *, field: str) -> _dt.datetime | None:
    """Parse an optional ISO-8601 string into a UTC datetime.

    Args:
        value: Raw body value.  ``None`` collapses to ``None``.
        field: Field name for the error message.

    Returns:
        A timezone-aware :class:`datetime.datetime`, or ``None`` when
        *value* is missing.

    Raises:
        ValidationError: When *value* is set but cannot be parsed.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be an ISO-8601 string when provided.")
    try:
        parsed = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.UTC)
    return parsed


@router.post("/api/pql/training/log")
async def api_pql_training_log(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Persist a one-shot training-run snapshot as an audit op-row.

    Mirrors what :func:`pointlessql.services.agent_runs.training_context.training_context`
    writes when an in-process agent block exits, but for HTTP-only
    callers (the Hermes plugin).  The agent enables MLflow autolog
    locally, runs its training loop, captures
    ``run.data.params + run.data.metrics``, and POSTs the pair here.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with required ``framework`` (str), ``params``
            (dict), ``metrics`` (dict); optional ``mlflow_run_id``
            (str), ``op_name`` (str, default ``"train_model"``,
            must be in :data:`VALID_OP_NAMES`), ``started_at`` /
            ``finished_at`` (ISO-8601), ``agent_run_id`` (str,
            falls back to ``X-Agent-Run-Id`` header).

    Returns:
        ``{"op_id": int, "agent_run_id": str, "training_params_json": str}``.

    Raises:
        ValidationError: When required fields are missing/malformed
            or when no ``agent_run_id`` is in scope.
    """
    body = body or {}

    framework = body.get("framework")
    params_raw = body.get("params")
    metrics_raw = body.get("metrics")
    op_name_raw = body.get("op_name", "train_model")
    mlflow_run_id_raw = body.get("mlflow_run_id")
    agent_run_id_raw = body.get("agent_run_id")
    started_at = _coerce_iso(body.get("started_at"), field="started_at")
    finished_at = _coerce_iso(body.get("finished_at"), field="finished_at")

    if not isinstance(framework, str) or not framework.strip():
        raise ValidationError("framework is required and must be a non-empty string.")
    if not isinstance(params_raw, dict):
        raise ValidationError("params is required and must be an object.")
    if not isinstance(metrics_raw, dict):
        raise ValidationError("metrics is required and must be an object.")
    if not isinstance(op_name_raw, str) or op_name_raw not in VALID_OP_NAMES:
        raise ValidationError(
            f"op_name must be one of {sorted(VALID_OP_NAMES)!r}.",
        )
    op_name: str = op_name_raw

    mlflow_run_id: str | None = None
    if mlflow_run_id_raw is not None:
        if not isinstance(mlflow_run_id_raw, str) or not mlflow_run_id_raw.strip():
            raise ValidationError("mlflow_run_id must be a non-empty string when provided.")
        mlflow_run_id = mlflow_run_id_raw.strip()

    body_run_id: str | None = None
    if agent_run_id_raw is not None:
        if not isinstance(agent_run_id_raw, str) or not agent_run_id_raw.strip():
            raise ValidationError("agent_run_id must be a non-empty string when provided.")
        body_run_id = agent_run_id_raw.strip()

    resolved_run_id = body_run_id or effective_agent_run_id(request)
    if not resolved_run_id:
        raise ValidationError(
            "agent_run_id is required (set X-Agent-Run-Id header or "
            "include agent_run_id in the body)."
        )

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ValidationError("audit DB is not bound; training-log requires a session factory.")

    # Strip non-stringifiable / non-numeric values defensively — we
    # store as JSON, so anything weird gets coerced via ``default=str``.
    params: dict[str, Any] = {str(k): v for k, v in params_raw.items()}  # type: ignore[reportUnknownVariableType]
    metrics: dict[str, Any] = {str(k): v for k, v in metrics_raw.items()}  # type: ignore[reportUnknownVariableType]
    training_params_json = json.dumps(
        {"params": params, "metrics": metrics},
        sort_keys=True,
        default=str,
    )

    now = _dt.datetime.now(_dt.UTC)
    started = started_at or now
    finished = finished_at or now

    op_params: dict[str, Any] = {
        "framework": framework.strip(),
        "op_name": op_name,
    }
    if mlflow_run_id:
        op_params["mlflow_run_id"] = mlflow_run_id

    def _persist() -> int:
        return record_operation(
            factory,
            agent_run_id=RunId(resolved_run_id),
            op_name=op_name,
            params=op_params,
            target_table=None,
            input_sha=None,
            rows_affected=None,
            delta_version_before=None,
            delta_version_after=None,
            started_at=started,
            finished_at=finished,
            error_message=None,
            training_params_json=training_params_json,
        )

    op_id = await asyncio.to_thread(_persist)

    await audit(
        request,
        "pql.training_log",
        f"run:{resolved_run_id}",
        {
            "op_id": op_id,
            "framework": framework.strip(),
            "mlflow_run_id": mlflow_run_id,
            "param_count": len(params),
            "metric_count": len(metrics),
        },
    )

    return {
        "op_id": op_id,
        "agent_run_id": resolved_run_id,
        "training_params_json": training_params_json,
    }
