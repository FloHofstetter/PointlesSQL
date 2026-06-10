"""``GET /api/sql/explain`` — cost gate + plan inspection.

Mirrors the parse + UC-SELECT-enforce front-half of the execute
route so a caller can't EXPLAIN a query whose tables they don't
have permission to read (that would leak schema information through
the plan).  Above the configured threshold, ``needs_approval`` flips
and a ``cost_gate.denied`` governance event fires so the audit-sink
trail captures the attempt.
"""

from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import effective_principal, get_uc_client, get_user
from pointlessql.api.sql.editor._helpers import short_sql_hash
from pointlessql.config import Settings
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.types import OpName, RunId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql"])


@router.get("/api/sql/explain")
async def api_sql_explain(request: Request, sql: str = "") -> dict[str, Any]:
    """Return a DuckDB EXPLAIN plan + heuristic cost for *sql*.

    Cost gate.  Mirrors the parse + UC-SELECT-enforce front-half of
    :func:`api_sql_execute` so the caller cannot EXPLAIN a query
    whose tables they don't have permission to read — that would
    leak schema information through the plan even without row
    materialisation.

    Above ``settings.sql.cost_gate_threshold_rows`` the response
    flips ``needs_approval`` to ``True``.  No enforcement happens
    here — the agent or run-detail UI decides what to do with the
    flag.

    Propagates :class:`AuthorizationError` from
    :func:`check_privilege` when the user lacks ``SELECT`` on a
    referenced table.

    Args:
        request: Incoming FastAPI request.  Reads
            ``request.state.user`` (auth middleware) and
            ``request.app.state.settings``.
        sql: The SELECT statement to analyse (passed as a query-
            string parameter for convenient ``curl`` usage).

    Returns:
        Plain dict with ``plan`` (the parsed JSON tree DuckDB
        emitted), ``cost`` (heuristic dict with
        ``max_cardinality`` / ``join_depth`` / ``cost`` /
        ``explanation``), ``needs_approval`` (bool against the
        configured threshold), ``threshold`` (the threshold echoed
        for client reasoning), and ``referenced_tables`` (the
        enforcement list).

    Raises:
        SQLExecutionError: SQL editor disabled, malformed SQL, or
            DuckDB rejected the EXPLAIN.
        CatalogNotFoundError: Referenced table unknown to
            soyuz-catalog or has no ``storage_location``.
    """
    from pointlessql.exceptions import CatalogNotFoundError, SQLExecutionError
    from pointlessql.pql import SQLParseError, prepare_sql
    from pointlessql.services.agent_runs import operation_context
    from pointlessql.services.sql import run_explain

    settings: Settings = request.app.state.settings
    if not settings.sql.enabled:
        raise SQLExecutionError("The SQL editor is disabled on this deployment.")

    query = (sql or "").strip()
    if not query:
        raise SQLExecutionError("The 'sql' query parameter must be a non-empty string.")

    # Per-run audit. If the caller is an agent (X-Agent-Run-Id
    # set), the explain attempt is recorded as an ``sql_explain``
    # operation row so an auditor can see what the agent saw before
    # deciding to execute or rewrite. Malformed UUIDs are silently
    # demoted to "no run id" so a typo doesn't 500 — the install-wide
    # ``audit_log`` row below still fires.
    run_id_raw = request.headers.get("X-Agent-Run-Id")
    run_id: str | None = None
    if run_id_raw:
        try:
            run_id = str(_uuid.UUID(run_id_raw))
        except ValueError:
            logger.debug(
                "explain: malformed X-Agent-Run-Id %r — skipping per-run audit", run_id_raw
            )
    factory = getattr(request.app.state, "session_factory", None) if run_id else None

    sql_hash = short_sql_hash(query)
    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, run_id),
        op_name=OpName.SQL_EXPLAIN,
        params={"sql_hash": sql_hash},
        target_table=None,
    ) as recorder:
        try:
            prepared = prepare_sql(query)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc

        recorder.extra_params["referenced_tables"] = list(prepared.refs)

        client = get_uc_client(request)
        user = get_user(request)
        email = effective_principal(request) or user.get("email", "")
        is_admin = user.get("is_admin", False)

        approved: dict[str, str] = {}
        for full_name in prepared.refs:
            parts = full_name.split(".")
            if len(parts) != 3:
                raise SQLExecutionError(
                    f"Internal error: expected 3-part name, got {full_name!r}.",
                )
            table_info = await client.get_table(parts[0], parts[1], parts[2])
            if not table_info:
                raise CatalogNotFoundError(f"Table not found: {full_name!r}")
            storage_location = table_info.get("storage_location")
            if not isinstance(storage_location, str) or not storage_location:
                raise CatalogNotFoundError(
                    f"Table {full_name!r} has no storage_location on soyuz-catalog.",
                )
            await check_privilege(client, email, is_admin, "table", full_name, SELECT)
            approved[full_name] = storage_location

        try:
            result = await asyncio.to_thread(run_explain, prepared.rewritten_sql, approved)
        except ValueError as exc:
            raise SQLExecutionError(str(exc)) from exc

        threshold = max(0, int(settings.sql.cost_gate_threshold_rows))
        needs_approval = threshold > 0 and result.cost.cost > threshold

        recorder.extra_params.update(
            {
                "cost": result.cost.cost,
                "max_cardinality": result.cost.max_cardinality,
                "join_depth": result.cost.join_depth,
                "threshold": threshold,
                "needs_approval": needs_approval,
            }
        )

        await audit(
            request,
            "query.explained",
            f"query:{sql_hash}",
            {
                "tables": result.referenced_tables,
                "cost": result.cost.cost,
                "needs_approval": needs_approval,
            },
        )
        response: dict[str, Any] = {
            "plan": result.plan,
            "cost": {
                "max_cardinality": result.cost.max_cardinality,
                "join_depth": result.cost.join_depth,
                "cost": result.cost.cost,
                "explanation": result.cost.explanation,
            },
            "needs_approval": needs_approval,
            "threshold": threshold,
            "referenced_tables": result.referenced_tables,
        }
        if needs_approval:
            response["cost_gate_trigger"] = {
                "explain": result.plan,
                "estimated_cost": result.cost.cost,
                "threshold": threshold,
                "engine": "duckdb",
                "referenced_tables": result.referenced_tables,
            }
            from pointlessql.services.workspace.governance import (
                EVENT_TYPE_COST_GATE_DENIED,
                emit_governance_event,
            )

            event_factory = getattr(request.app.state, "session_factory", None)
            try:
                await emit_governance_event(
                    EVENT_TYPE_COST_GATE_DENIED,
                    {
                        "principal": email,
                        "estimated_cost": result.cost.cost,
                        "threshold": threshold,
                        "referenced_tables": result.referenced_tables,
                        "query_hash": sql_hash,
                    },
                    settings=settings,
                    session_factory=event_factory,
                )
            except Exception:  # noqa: BLE001 — emit must never raise
                logger.exception("cost_gate.denied emit failed for %s", sql_hash)
        return response
