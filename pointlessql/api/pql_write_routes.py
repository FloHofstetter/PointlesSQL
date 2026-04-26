"""PQL write-side endpoints — Sprint 13.11.11.

Closes the read-only gap in the agent's tool surface.  Until this
sprint, ``hermes-plugin-pointlessql`` exposed ``pql_query`` (read SQL)
plus the Family-A introspection set (Sprint 13.11.1-3), but the agent
had **no way** to drive a Bronze → Silver → Gold pipeline through
Hermes — every write needed a side-channel script.  The 2026-04-26
walkthrough surfaced this when ``gpt-5-mini`` correctly identified that
``pql.autoload`` was unreachable from the chat adapter (see
``project_plugin_write_tools_gap.md``).

This module hosts every ``POST /api/pql/...`` write route:

* ``POST /api/pql/autoload`` — file-bytes-to-bronze ingest, mirrors
  :meth:`pointlessql.pql.pql.PQL.autoload`.
* ``POST /api/pql/write_table`` — runs a SELECT, materialises the rows
  as a pandas frame, and pipes them through
  :meth:`~pointlessql.pql.pql.PQL.write_table`.
* ``POST /api/pql/merge`` — runs a SELECT, materialises as pandas, then
  upserts (or SCD-2 appends) into an existing Delta target via
  :meth:`~pointlessql.pql.pql.PQL.merge`.
* ``POST /api/pql/drop_table`` — admin-only, soyuz ``DELETE`` passthrough.

All four sit behind the principal-aware
:func:`pointlessql.services.authorization.check_privilege` enforcement
plus the Sprint-13.8 forced audit trail: rows of
``agent_run_operations`` are emitted by the underlying primitives, so a
write that errors halfway still leaves a correct trace.

The write routes deliberately do not duplicate the SQL editor's parse
+ enforce code path verbatim — instead, ``write_table`` and ``merge``
reuse the same ``prepare_sql`` + ``register_delta_view`` building
blocks so the SELECT side stays consistent with ``POST /api/sql/execute``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.services.authorization import (
    MODIFY,
    SELECT,
    USE_SCHEMA,
    check_privilege,
)
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pql-write"])


# ─── helpers ──────────────────────────────────────────────────────────


def _split_three_part(full_name: str) -> tuple[str, str, str]:
    """Validate and split a ``catalog.schema.table`` UC reference.

    Local copy of the same helper in
    :mod:`pointlessql.api.pql_introspect_routes` — duplicated rather
    than re-exported so the two route modules stay independently
    importable.  Both copies share the same shape and the same
    error message.

    Args:
        full_name: 3-part dot-separated identifier.

    Returns:
        ``(catalog, schema, table)``.

    Raises:
        ValidationError: When the identifier has fewer than three
            non-empty parts.
    """
    parts = [p.strip() for p in full_name.split(".")]
    if len(parts) != 3 or not all(parts):
        raise ValidationError(
            "table must be a three-part UC name 'catalog.schema.table'",
        )
    return parts[0], parts[1], parts[2]


async def _approve_select_refs(request: Request, refs: list[str]) -> dict[str, str]:
    """Run SELECT enforcement on every reference and return storage map.

    Args:
        request: Incoming FastAPI request — supplies the
            principal-scoped UC client and the auth state.
        refs: 3-part ``catalog.schema.table`` names the SELECT touches.

    Returns:
        Mapping ``full_name → storage_location`` for every ref the
        caller is allowed to read.

    Raises:
        ValidationError: When a ref is not a 3-part name.
        CatalogNotFoundError: When a ref is unknown to soyuz-catalog
            or has no ``storage_location``.
        AuthorizationError: When the principal lacks ``SELECT`` on a
            ref (raised by :func:`check_privilege`).
    """  # noqa: DOC502,DOC503 — AuthorizationError raised inside check_privilege
    uc_client = get_uc_client(request)
    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    is_admin = user.get("is_admin", False)
    approved: dict[str, str] = {}
    for full_name in refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            raise ValidationError(
                f"Internal error: expected 3-part name, got {full_name!r}.",
            )
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            raise CatalogNotFoundError(f"Table not found: {full_name!r}")
        storage = info.get("storage_location")
        if not isinstance(storage, str) or not storage:
            raise CatalogNotFoundError(
                f"Table {full_name!r} has no storage_location on soyuz-catalog.",
            )
        await check_privilege(uc_client, email, is_admin, "table", full_name, SELECT)
        approved[full_name] = storage
    return approved


async def _check_write_target(request: Request, target: str, *, must_exist: bool) -> bool:
    """Enforce write privilege on *target* and report whether it exists.

    The autoload + write-table flows tolerate a missing target — the
    primitive bootstraps it from the parent schema's ``storage_root``.
    The merge flow requires it to exist (the merge semantics need a
    live Delta log to apply changes against).  ``must_exist=True``
    makes the missing-target case raise.

    When the target already exists we require ``MODIFY`` on it; when
    it does not we require ``USE SCHEMA`` on the parent so the agent
    can land bytes underneath.

    Args:
        request: Incoming FastAPI request.
        target: 3-part UC name that the operation will write to.
        must_exist: When ``True``, raise if the target does not exist.

    Returns:
        ``True`` if the target already exists, ``False`` otherwise.

    Raises:
        ValidationError: When *target* is malformed.
        CatalogNotFoundError: When *target* is missing and
            ``must_exist`` is ``True``.
        AuthorizationError: When the principal lacks the required
            privilege.
    """  # noqa: DOC502,DOC503 — ValidationError + AuthorizationError raised inside helpers
    catalog, schema_name, table_name = _split_three_part(target)
    uc_client = get_uc_client(request)
    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    is_admin = user.get("is_admin", False)
    target_exists = True
    try:
        info = await uc_client.get_table(catalog, schema_name, table_name)
        if not info:
            target_exists = False
    except CatalogNotFoundError:
        target_exists = False
    if not target_exists and must_exist:
        raise CatalogNotFoundError(
            f"Target table {target!r} does not exist — bootstrap it via "
            "POST /api/pql/write_table or POST /api/pql/autoload first.",
        )
    if target_exists:
        await check_privilege(uc_client, email, is_admin, "table", target, MODIFY)
    else:
        await check_privilege(
            uc_client,
            email,
            is_admin,
            "schema",
            f"{catalog}.{schema_name}",
            USE_SCHEMA,
        )
    return target_exists


def _materialise_select_to_pandas(sql: str, approved: dict[str, str]) -> Any:
    """Run *sql* via DuckDB and return the result as a pandas DataFrame.

    Mirrors :func:`pointlessql.api.sql_routes.run_sql_export_sync` but
    skips the row-cap step — write/merge SQL must materialise the full
    result so no rows are silently dropped before the Delta write.  The
    DuckDB connection is created and torn down per call: the writes are
    short-lived, and the SQL editor's cancel registry is irrelevant
    here.

    Args:
        sql: The SQL the route already authorised against *approved*.
        approved: ``full_name → storage_location`` map produced by
            :func:`_approve_select_refs`.

    Returns:
        A :class:`pandas.DataFrame` carrying the full SELECT result.

    Raises:
        SQLExecutionError: When DuckDB rejects the SQL (column missing,
            type mismatch, …) — re-raised so the centralised error
            handler returns RFC 9457.
    """
    import duckdb  # noqa: PLC0415 — local import keeps the module lazy

    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql.engine import register_delta_view
    from pointlessql.pql.sql_parser import prepare_sql

    prepared = prepare_sql(sql)
    conn = duckdb.connect()
    try:
        for ref in prepared.refs:
            register_delta_view(conn, ref, approved[ref])
        try:
            arrow_table: Any = conn.execute(prepared.rewritten_sql).to_arrow_table()
        except duckdb.Error as exc:
            raise SQLExecutionError(str(exc)) from exc
    finally:
        conn.close()
    return arrow_table.to_pandas()


def _build_pql(request: Request, *, principal: str, agent_run_id: str | None) -> Any:
    """Construct a sync :class:`PQL` instance for the current request.

    Imports lazily so the module stays cheap to load — a thin route
    module shouldn't pull in ``deltalake`` + ``pandas`` at startup.

    Args:
        request: Incoming FastAPI request — read for ``app.state.settings``.
        principal: The effective principal forwarded as ``X-Principal``
            on every soyuz call PQL makes.
        agent_run_id: Optional run id; when present every PQL primitive
            writes one ``agent_run_operations`` row (Sprint 13.8 forced
            trail).

    Returns:
        A configured :class:`PQL` instance ready for sync dispatch
        from :func:`asyncio.to_thread`.
    """
    from pointlessql.pql.pql import PQL  # noqa: PLC0415 — lazy

    settings: Settings = request.app.state.settings
    return PQL(
        settings=settings,
        principal=principal or None,
        agent_run_id=agent_run_id,
    )


# ─── routes ───────────────────────────────────────────────────────────


@router.post("/api/pql/autoload")
async def api_pql_autoload(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Lift files from a Volume directory into a Delta target.

    Mirrors :meth:`pointlessql.pql.pql.PQL.autoload` over HTTP.  Used
    by the ``pql_autoload`` Hermes tool so a working agent can fold a
    raw-drop directory into bronze without leaving the chat surface.

    Privilege model: when the target already exists the principal
    needs ``MODIFY`` on it; when the target is missing the route
    accepts ``USE SCHEMA`` on the parent schema, mirroring how the
    primitive itself bootstraps a fresh Delta log under the parent's
    ``storage_root`` on the first successful append.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``source_path``, ``target``,
            ``source_system`` (optional), and ``file_format`` (optional,
            default ``"auto"``).

    Returns:
        ``{"target", "files_scanned", "files_ingested", "files_skipped",
        "rows_ingested"}`` — the dict :meth:`PQL.autoload` returns.

    Raises:
        ValidationError: When required fields are missing or malformed.
        AuthorizationError: When the principal lacks ``MODIFY`` /
            ``USE SCHEMA`` (raised by :func:`check_privilege`).
    """  # noqa: DOC502,DOC503 — AuthorizationError raised inside check_privilege
    source_path = (body or {}).get("source_path", "")
    target = (body or {}).get("target", "")
    source_system = (body or {}).get("source_system", "")
    file_format = (body or {}).get("file_format", "auto")

    if not isinstance(source_path, str) or not source_path.strip():
        raise ValidationError("source_path is required and must be a string.")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if not isinstance(source_system, str):
        raise ValidationError("source_system must be a string when set.")
    if file_format not in ("auto", "parquet", "csv", "json"):
        raise ValidationError(
            "file_format must be one of 'auto', 'parquet', 'csv', 'json'.",
        )

    await _check_write_target(request, target, must_exist=False)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        pql = _build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.autoload(
            source_path=source_path,
            target=target,
            source_system=source_system,
            file_format=file_format,
        )

    result = await asyncio.to_thread(_run)
    await audit(
        request,
        "pql.autoload",
        f"table:{target}",
        {
            "source_path": source_path,
            "files_ingested": result.get("files_ingested"),
            "rows_ingested": result.get("rows_ingested"),
        },
    )
    return result


_VALID_WRITE_MODES = ("error", "append", "overwrite", "ignore")


@router.post("/api/pql/write_table")
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
            (3-part UC name), and ``mode`` (one of ``"error"`` /
            ``"append"`` / ``"overwrite"`` / ``"ignore"``, default
            ``"overwrite"``).

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
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    sql = (body or {}).get("sql", "")
    target = (body or {}).get("target", "")
    mode = (body or {}).get("mode", "overwrite")

    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("sql is required and must be a string.")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if mode not in _VALID_WRITE_MODES:
        raise ValidationError(
            f"mode must be one of {_VALID_WRITE_MODES!r}.",
        )

    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    approved = await _approve_select_refs(request, prepared.refs)
    await _check_write_target(request, target, must_exist=False)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        df = _materialise_select_to_pandas(sql, approved)
        pql = _build_pql(request, principal=email, agent_run_id=agent_run_id)
        pql.write_table(df, target, mode=mode)
        return {
            "target": target,
            "mode": mode,
            "rows_written": int(len(df)),
        }

    result = await asyncio.to_thread(_run)
    await audit(
        request,
        "pql.write_table",
        f"table:{target}",
        {
            "mode": mode,
            "rows_written": result["rows_written"],
            "source_refs": prepared.refs,
        },
    )
    return result


_VALID_MERGE_STRATEGIES = ("upsert", "scd2")


@router.post("/api/pql/merge")
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
            UC name), ``on`` (non-empty list of merge-key columns), and
            ``strategy`` (``"upsert"`` default, or ``"scd2"``).

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
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    sql = (body or {}).get("sql", "")
    target = (body or {}).get("target", "")
    on_raw = (body or {}).get("on", [])
    strategy = (body or {}).get("strategy", "upsert")

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

    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    approved = await _approve_select_refs(request, prepared.refs)
    await _check_write_target(request, target, must_exist=True)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        df = _materialise_select_to_pandas(sql, approved)
        pql = _build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.merge(df, target, on=on, strategy=strategy)

    result = await asyncio.to_thread(_run)
    await audit(
        request,
        "pql.merge",
        f"table:{target}",
        {
            "strategy": strategy,
            "on": on,
            "source_refs": prepared.refs,
        },
    )
    return result


@router.post("/api/pql/drop_table", status_code=200)
async def api_pql_drop_table(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Delete a Unity Catalog table — admin-only.

    Mirrors soyuz-catalog's
    ``DELETE /catalogs/{c}/schemas/{s}/tables/{t}`` route.  Wrapping
    it as ``POST /api/pql/drop_table`` keeps the agent's surface
    JSON-bodied (every other write tool POSTs JSON, so consistency
    matters more than REST verb purity here) and lets the
    :func:`require_admin` gate do the work — drops are destructive
    and not in the working-agent's privilege envelope.

    The Delta storage bytes underneath the catalog row are **not**
    removed by this route — that is soyuz's call, and the current
    soyuz behaviour is registry-only deletion.  An operator is still
    expected to clean up the storage directory manually if needed.

    Args:
        request: Incoming FastAPI request — must carry a cookie /
            api-key with admin role.
        body: JSON body with ``full_name`` (3-part UC name).

    Returns:
        ``{"target", "deleted": True}`` on success.

    Raises:
        ValidationError: When ``full_name`` is missing or malformed.
        AuthorizationError: When the caller is not an admin (raised
            by :func:`require_admin`).
        CatalogNotFoundError: When the target is unknown to soyuz.
    """  # noqa: DOC502,DOC503 — exceptions bubble up to the centralised handler
    require_admin(request)

    full_name = (body or {}).get("full_name", "")
    if not isinstance(full_name, str) or not full_name.strip():
        raise ValidationError("full_name is required and must be a string.")
    catalog, schema_name, table_name = _split_three_part(full_name)

    uc_client = get_uc_client(request)
    await uc_client.delete_table(catalog, schema_name, table_name)
    await audit(
        request,
        "pql.drop_table",
        f"table:{full_name}",
        {"deleted": True},
    )
    return {"target": full_name, "deleted": True}


__all__ = ["router"]
