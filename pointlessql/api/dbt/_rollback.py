"""Auto-rollback of dbt-driven model writes on test failure.

Two helpers: a thin ``PQL.rollback`` wrapper that owns the lazy
PQL import, and the async coordinator that walks
``agent_run_operations`` for every ``dbt_model`` op of a failing run
and undoes each write.  Used only by the test-route path —
auto-rollback never fires on the bare ``dbt run`` route.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import get_user
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.services._executor import run_sync
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED,
    emit_governance_event,
)
from pointlessql.types import OpName


def invoke_pql_rollback(
    settings: Any,
    *,
    principal: str,
    agent_run_id: str,
    target: str,
    op_ordinal: int,
) -> Any:
    """Call ``PQL.rollback`` for one target inside ``asyncio.to_thread``.

    Lazy-imports :class:`PQL` so the dbt routes don't pay for the deltalake
    + soyuz client cold-start when auto-rollback is unused.

    Args:
        settings: Resolved ``Settings`` instance.
        principal: Caller's email; written into the rollback op's audit row.
        agent_run_id: Run id whose write is being undone *and* on which
            the rollback op itself is recorded.  Same id by design so
            the dbt-test failure and its auto-undo land on the same
            timeline.
        target: ``"catalog.schema.table"`` of the model to roll back.
        op_ordinal: Ordinal of the matching ``dbt_model`` op in the run.

    Returns:
        The :class:`pointlessql.pql._rollback.RollbackResult`.
    """
    from pointlessql.pql import PQL  # noqa: PLC0415 — lazy

    pql = PQL(
        settings=settings,
        principal=principal or None,
        agent_run_id=agent_run_id,
    )
    return pql.rollback(
        target,
        before_run=agent_run_id,
        op_ordinal=op_ordinal,
        allow_force=False,
    )


async def auto_rollback_on_error(
    request: Request,
    *,
    agent_run_id: str,
    err_failures: int,
    auto_rollback: bool,
) -> dict[str, Any] | None:
    """Roll back every dbt model written under ``agent_run_id`` on error fails.

    Walks ``agent_run_operations`` for all ``op_name='dbt_model'`` rows
    in the run, newest-first, and invokes ``pql.rollback`` for each one.
    Per-target failures (``RollbackStale``, ``RollbackAmbiguous``, …)
    land in the ``failed`` list rather than aborting the sweep — every
    target gets its own try/except hull.

    The depth of the unwind is conservative (every model written this
    run) rather than depends_on-traversal-precise.  Reason: walking the
    failing-test ``depends_on`` graph would skip transitively dependent
    downstream models that the agent also produced this run, which is
    the wrong direction at safety time.  Auto-rollback errs toward
    over-undo; the agent can always re-run on the next turn.

    Args:
        request: Incoming FastAPI request.
        agent_run_id: The dbt-test run whose model writes to undo.
        err_failures: Count of error-severity failing tests.  When 0
            we no-op even if ``auto_rollback`` is set — the run is
            healthy, no rollback needed.
        auto_rollback: The body flag.  ``False`` → no-op.

    Returns:
        ``None`` when no rollback was attempted.  Otherwise an
        ``{"enabled", "targets_attempted", "succeeded", "failed"}``
        dict suitable for the response envelope.
    """
    if not auto_rollback or err_failures == 0:
        return None

    settings = request.app.state.settings
    factory = request.app.state.session_factory
    user = get_user(request)
    principal = str(user.get("email") or "")
    workspace_id = int(getattr(request.state, "workspace_id", 1))

    targets: list[tuple[str, int]] = []
    with factory() as session:
        rows = session.scalars(
            select(AgentRunOperation)
            .where(AgentRunOperation.agent_run_id == agent_run_id)
            .where(AgentRunOperation.op_name == OpName.DBT_MODEL)
            .where(AgentRunOperation.target_table.is_not(None))
            .order_by(AgentRunOperation.ordinal.desc()),
        ).all()
        targets = [(str(r.target_table), int(r.ordinal)) for r in rows]

    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for target, ordinal in targets:
        try:
            result = await run_sync(
                invoke_pql_rollback,
                settings,
                principal=principal,
                agent_run_id=agent_run_id,
                target=target,
                op_ordinal=ordinal,
            )
            succeeded.append(
                {
                    "target": target,
                    "ordinal": ordinal,
                    "version_before": result.version_before,
                    "version_after": result.version_after,
                    "target_version_restored": result.target_version_restored,
                },
            )
        except Exception as exc:  # noqa: BLE001 — refusal-tolerant by design
            # bare-broad-ok: refusal info is captured into failed[] for the
            # response payload; per-target rollback continues for siblings
            failed.append(
                {
                    "target": target,
                    "ordinal": ordinal,
                    "reason": exc.__class__.__name__,
                    "message": str(exc),
                },
            )

    await emit_governance_event(
        EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED,
        {
            "agent_run_id": agent_run_id,
            "targets_attempted": [t for t, _ in targets],
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
        },
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )

    return {
        "enabled": True,
        "targets_attempted": [t for t, _ in targets],
        "succeeded": succeeded,
        "failed": failed,
    }
