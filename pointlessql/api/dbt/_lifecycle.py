"""Auto-spawned ``AgentRun`` lifecycle for dbt CLI invocations.

When a caller invokes ``/api/dbt/run`` or ``/api/dbt/test`` without
supplying an existing ``agent_run_id``, the route auto-creates a
run keyed to the user's email so every dbt operation lands under
a known parent.  ``_finish_owned_run`` closes it; ``_result_payload``
builds the common executor-envelope response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.models.agent._runs import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    AgentRun,
)
from pointlessql.services.dbt import DBTRunResult


def create_owned_run(request: Request, user_email: str) -> str:
    """Auto-create an :class:`AgentRun` keyed to the calling user.

    Used when the caller did not supply an ``agent_run_id`` — we still
    want every dbt operation to land under a known parent so the
    cockpit can render the per-run timeline.

    Args:
        request: Incoming request (provides session + workspace).
        user_email: Calling user's email; recorded as ``principal``.

    Returns:
        The newly-minted run id.
    """
    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    with factory() as session:
        row = AgentRun(
            id=run_id,
            workspace_id=workspace_id,
            principal=user_email,
            agent_id="dbt-cli",
            notebook_path="dbt:run",
            source_snapshot_sha=None,
            status=STATUS_RUNNING,
            started_at=started_at,
        )
        session.add(row)
        session.commit()
    return run_id


def finish_owned_run(
    request: Request,
    run_id: str,
    *,
    succeeded: bool,
    exit_code: int,
) -> None:
    """Mark an auto-created run terminal.

    Args:
        request: Incoming request (provides session).
        run_id: The auto-created run id.
        succeeded: True if no node failed, else False.
        exit_code: dbt's process exit code, recorded on the row.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            return
        row.status = STATUS_SUCCEEDED if succeeded else STATUS_FAILED
        row.finished_at = datetime.now(UTC)
        row.exit_code = exit_code
        session.commit()


def result_payload(result: DBTRunResult, agent_run_id: str | None) -> dict[str, Any]:
    """Common envelope for the executor's CLI outcome.

    Args:
        result: Executor outcome.
        agent_run_id: The audited run id (``None`` for compile/deps).

    Returns:
        JSON-shaped dict with stable field names.
    """
    return {
        "agent_run_id": agent_run_id,
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": result.duration_seconds,
        "truncated_stdout": result.truncated_stdout,
        "truncated_stderr": result.truncated_stderr,
        "manifest_path": str(result.manifest_path),
        "run_results_path": str(result.run_results_path),
    }
