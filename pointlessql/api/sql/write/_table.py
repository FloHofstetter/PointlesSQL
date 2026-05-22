# pyright: reportPrivateUsage=false
"""``POST /api/pql/write_table`` + ``POST /api/pql/merge`` — pandas-materialised writes.

Both routes share the SELECT-materialise-pandas-pass-to-PQL skeleton;
keeping them in one file makes the symmetry obvious.  ``write_table``
bootstraps a Delta log on first call; ``merge`` requires the target
to already exist.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.sql.write._helpers import (
    _approve_select_refs,
    _check_write_target,
)
from pointlessql.exceptions import ValidationError

router = APIRouter(tags=["pql-write"])


_VALID_WRITE_MODES = ("error", "append", "overwrite", "ignore")
_VALID_MERGE_STRATEGIES = ("upsert", "scd2")


@router.post("/api/pql/write_table", responses=STANDARD_ERROR_RESPONSES)
async def api_pql_write_table(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run a SELECT, write the result rows to a Delta target.

    Mirrors :meth:`pointlessql.pql.pql.PQL.write_table` over HTTP, with
    one twist: the agent supplies the source rows as a SELECT statement
    rather than uploading a pandas frame — this keeps the request body
    JSON-shaped and removes the agent's need to construct a binary
    payload.  The server runs the SELECT against the SQL-editor
    pipeline (parse, UC SELECT enforcement, DuckDB execute) and only
    then hands the resulting frame to the write primitive.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``sql`` (the source SELECT), ``target``
            (3-part UC name), ``mode`` (one of ``"error"`` /
            ``"append"`` / ``"overwrite"`` / ``"ignore"``, default
            ``"overwrite"``), and optional ``source_model_uri``
            (registered-model URI of the form
            ``models:/cat.sch.model/<version>`` when *df* is the
            output of inference against a model; threaded into
            ``lineage_row_edges.source_model_uri``).

    Returns:
        ``{"target", "mode", "rows_written"}`` — the row count is
        sourced from the materialised pandas frame so the agent gets
        an ack of how much landed without a follow-up ``COUNT(*)``.

    Raises:
        ValidationError: When required fields are missing or malformed.
        AuthorizationError: When the principal lacks ``SELECT`` on a
            referenced table or ``MODIFY`` / ``USE SCHEMA`` on the
            target.
        CatalogNotFoundError: When a referenced table is unknown.
        SQLExecutionError: When DuckDB rejects the SELECT.
    """  # noqa: DOC502,DOC503 — exceptions bubble up to the centralised handler
    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql import SQLParseError, prepare_sql

    sql = (body or {}).get("sql", "")
    target = (body or {}).get("target", "")
    mode = (body or {}).get("mode", "overwrite")
    source_model_uri_raw = (body or {}).get("source_model_uri")

    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("sql is required and must be a string.")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if mode not in _VALID_WRITE_MODES:
        raise ValidationError(
            f"mode must be one of {_VALID_WRITE_MODES!r}.",
        )
    source_model_uri: str | None = None
    if source_model_uri_raw is not None:
        if not isinstance(source_model_uri_raw, str) or not source_model_uri_raw.strip():
            raise ValidationError("source_model_uri must be a non-empty string when provided.")
        source_model_uri = source_model_uri_raw.strip()

    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    approved = await _approve_select_refs(request, prepared.refs)
    await _check_write_target(request, target, must_exist=False)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    # When the agent declares this write as inference output, auto-derive
    # source_table_fqn from the SELECT refs so the row-edge grain in
    # lineage_row_edges has somewhere to anchor ('s primitive
    # only persists source_model_uri alongside a source table).  Skip
    # auto-derive when the SELECT references multiple tables — ambiguous.
    derived_source_fqn: str | None = None
    if source_model_uri and len(prepared.refs) == 1:
        derived_source_fqn = prepared.refs[0]

    def _run() -> dict[str, Any]:
        # Lookup via the write package so monkeypatched helpers in
        # tests are picked up at call time (the package re-export
        # binding wins over the direct submodule import).
        from pointlessql.api.sql import write as _write_pkg

        df = _write_pkg._materialise_select_to_pandas(sql, approved)
        pql = _write_pkg._build_pql(request, principal=email, agent_run_id=agent_run_id)
        pql.write_table(
            df,
            target,
            mode=mode,
            source_table_fqn=derived_source_fqn,
            source_model_uri=source_model_uri,
        )
        return {
            "target": target,
            "mode": mode,
            "rows_written": int(len(df)),
        }

    result = await asyncio.to_thread(_run)
    audit_extra: dict[str, Any] = {
        "mode": mode,
        "rows_written": result["rows_written"],
        "source_refs": prepared.refs,
    }
    if source_model_uri:
        audit_extra["source_model_uri"] = source_model_uri
    await audit(
        request,
        "pql.write_table",
        f"table:{target}",
        audit_extra,
    )
    return result


@router.post("/api/pql/merge", responses=STANDARD_ERROR_RESPONSES)
async def api_pql_merge(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run a SELECT, merge the result into an existing Delta target.

    Mirrors :meth:`pointlessql.pql.pql.PQL.merge` over HTTP.  The
    target must already exist (the merge semantics need a live Delta
    log to apply changes against); use ``POST /api/pql/write_table``
    or ``POST /api/pql/autoload`` to bootstrap.

    Two strategies match the primitive: ``"upsert"`` (key match →
    update non-key columns; otherwise insert) and ``"scd2"``
    (append-only history with ``_valid_from`` / ``_valid_to`` /
    ``_is_current``).

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``sql`` (source SELECT), ``target`` (3-part
            UC name), ``on`` (non-empty list of merge-key columns),
            ``strategy`` (``"upsert"`` default, or ``"scd2"``), and
            optional ``source_model_uri`` (registered-
            model URI when the merge writes inference outputs into an
            existing predictions table).

    Returns:
        The merge stats dict from :meth:`PQL.merge` — carries
        ``strategy`` plus the deltalake counts (``num_target_rows_inserted``,
        ``num_target_rows_updated``, …).  SCD-2 also includes
        ``rows_appended``.

    Raises:
        ValidationError: When required fields are missing or malformed.
        AuthorizationError: When the principal lacks ``SELECT`` on a
            referenced table or ``MODIFY`` on the target.
        CatalogNotFoundError: When the target or a referenced table is
            unknown.
        SQLExecutionError: When DuckDB rejects the source SELECT.
    """  # noqa: DOC502,DOC503 — exceptions bubble up to the centralised handler
    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql import SQLParseError, prepare_sql

    sql = (body or {}).get("sql", "")
    target = (body or {}).get("target", "")
    on_raw = (body or {}).get("on", [])
    strategy = (body or {}).get("strategy", "upsert")
    source_model_uri_raw = (body or {}).get("source_model_uri")

    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("sql is required and must be a string.")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if not isinstance(on_raw, list) or not on_raw:
        raise ValidationError("on must be a non-empty list of column names.")
    on: list[str] = []
    for item in on_raw:  # type: ignore[reportUnknownVariableType]
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(
                "on entries must be non-empty column-name strings.",
            )
        on.append(item)
    if strategy not in _VALID_MERGE_STRATEGIES:
        raise ValidationError(
            f"strategy must be one of {_VALID_MERGE_STRATEGIES!r}.",
        )
    source_model_uri: str | None = None
    if source_model_uri_raw is not None:
        if not isinstance(source_model_uri_raw, str) or not source_model_uri_raw.strip():
            raise ValidationError("source_model_uri must be a non-empty string when provided.")
        source_model_uri = source_model_uri_raw.strip()

    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    approved = await _approve_select_refs(request, prepared.refs)
    await _check_write_target(request, target, must_exist=True)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    derived_source_fqn: str | None = None
    if source_model_uri and len(prepared.refs) == 1:
        derived_source_fqn = prepared.refs[0]

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql import write as _write_pkg

        df = _write_pkg._materialise_select_to_pandas(sql, approved)
        pql = _write_pkg._build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.merge(
            df,
            target,
            on=on,
            strategy=strategy,
            source_table_fqn=derived_source_fqn,
            source_model_uri=source_model_uri,
        )

    result = await asyncio.to_thread(_run)
    audit_extra: dict[str, Any] = {
        "strategy": strategy,
        "on": on,
        "source_refs": prepared.refs,
    }
    if source_model_uri:
        audit_extra["source_model_uri"] = source_model_uri
    await audit(
        request,
        "pql.merge",
        f"table:{target}",
        audit_extra,
    )
    return result
