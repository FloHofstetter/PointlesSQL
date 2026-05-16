"""Agent-run lifecycle helpers shared by every write branch.

Every editor write opens a one-shot ``agent_run`` row with
``agent_id='sql-editor'`` *before* invoking the primitive, and
finalises the row with terminal status *after* — so the audit trail
captures both success and failure paths.  DDL branches additionally
emit an ``agent_run_operations`` row because the soyuz client calls
don't flow through PQL's ``operation_context``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pointlessql.api.sql._dispatcher._types import DispatchContext
from pointlessql.models.agent._runs import STATUS_RUNNING, AgentRun

logger = logging.getLogger(__name__)


async def start_editor_agent_run(
    ctx: DispatchContext, *, target_fqn: str
) -> str:
    """Create a one-shot ``agent_run`` row for an interactive editor write.

    Each editor write statement gets its own run with
    ``agent_id='sql-editor'``.  The PQL primitives (``write_table``,
    ``update``, ``delete``, ``merge``) detect the run id via the
    constructor kwarg threaded through ``_build_pql`` and emit
    ``agent_run_operations`` against it automatically.

    Args:
        ctx: Dispatcher context.
        target_fqn: The write target — recorded on
            ``tables_touched`` so the runs-list page surfaces it
            without joining ``agent_run_operations``.

    Returns:
        The new run's UUID string.
    """
    factory = ctx.request.app.state.session_factory
    run_id = str(uuid.uuid4())
    workspace_id = int(getattr(ctx.request.state, "workspace_id", 1))
    sql_sha = hashlib.sha256(ctx.sql.encode("utf-8")).hexdigest()
    started_at = datetime.now(UTC)

    def _insert() -> None:
        with factory() as session:
            row = AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal=ctx.actor_email or None,
                agent_id="sql-editor",
                notebook_path="<sql-editor>",
                source_snapshot_sha=sql_sha,
                status=STATUS_RUNNING,
                cost_est=None,
                tables_touched=json.dumps([target_fqn]),
                started_at=started_at,
                runtime_versions=json.dumps(
                    {"sql-editor": "63.0", "stmt_type": ctx.stype.value},
                    sort_keys=True,
                ),
            )
            session.add(row)
            session.commit()

    await asyncio.to_thread(_insert)
    return run_id


async def finish_agent_run(
    ctx: DispatchContext,
    run_id: str,
    *,
    status: Literal["succeeded", "failed"],
    error: str | None = None,
) -> None:
    """Update *run_id* with terminal status + finish timestamp.

    Best-effort: a failed update path is logged but does not
    further raise — the underlying primitive's failure is the
    user-visible event.

    Args:
        ctx: Dispatcher context.
        run_id: UUID of the run to finalise.
        status: Terminal value, ``'succeeded'`` or ``'failed'``.
        error: Optional truncated error message recorded into
            ``denied_reason`` for failed runs.
    """
    factory = ctx.request.app.state.session_factory

    def _update() -> None:
        from sqlalchemy import select

        with factory() as session:
            row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if row is None:  # pragma: no cover — race we ignore
                return
            row.status = status
            row.finished_at = datetime.now(UTC)
            if status == "failed" and error:
                row.denied_reason = error[:1024]
            session.commit()

    try:
        await asyncio.to_thread(_update)
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("sql-editor agent_run finish update failed for %s", run_id)


async def emit_ddl_op(
    ctx: DispatchContext,
    *,
    run_id: str,
    op_name_value: str,
    target_fqn: str,
    extras: dict[str, Any],
) -> None:
    """Record a single ``agent_run_operations`` row for a DDL action.

    DDL flows through the soyuz client (not a PQL primitive), so
    there is no :func:`operation_context` wrapper inside the
    catalog call.  This helper writes the op row directly so the
    audit trail has parity with DML.

    Args:
        ctx: Dispatcher context.
        run_id: Owning agent_run UUID.
        op_name_value: One of ``'drop_table'``, ``'create_schema'``,
            ``'drop_schema'``, ``'alter_table'``.  Must already be
            in the ``ck_agent_run_operations_op_name`` CHECK set
            (alembic ``ee3f6h8j0l2n``).
        target_fqn: 3-part FQN for tables, 2-part for schemas.
        extras: Free-form dict merged into ``params_json``.
    """
    from sqlalchemy import text

    factory = ctx.request.app.state.session_factory
    op_id = str(uuid.uuid4())
    started = datetime.now(UTC)
    params = {"target": target_fqn, **extras}

    def _insert() -> None:
        with factory() as session:
            session.execute(
                text(
                    "INSERT INTO agent_run_operations "
                    "(id, workspace_id, agent_run_id, op_name, params_json, "
                    "target_table, started_at, finished_at, status) "
                    "VALUES (:id, :ws, :run, :name, :params, :target, "
                    ":start, :finish, 'succeeded')",
                ),
                {
                    "id": op_id,
                    "ws": int(getattr(ctx.request.state, "workspace_id", 1)),
                    "run": run_id,
                    "name": op_name_value,
                    "params": json.dumps(params, sort_keys=True),
                    "target": target_fqn,
                    "start": started,
                    "finish": datetime.now(UTC),
                },
            )
            session.commit()

    try:
        await asyncio.to_thread(_insert)
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("sql-editor DDL op record failed for run=%s op=%s", run_id, op_name_value)
