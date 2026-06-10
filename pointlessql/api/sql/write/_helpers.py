# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Shared helpers used by every ``/api/pql/...`` write surface.

Two SELECT-side helpers (auth gate + DuckDB materialise) plus the
PQL-builder used to thread principal + agent-run id into the
:class:`pointlessql.pql.pql.PQL` instance that ultimately writes the
Delta target.

The leading underscores on the symbol names are preserved so the
cross-module callers in ``sql.editor._batch``, ``sql._dispatcher._dml``
and ``pql.sql_merge_translator`` continue to import unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
from pointlessql.config import Settings
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.services.authorization import (
    MODIFY,
    SELECT,
    USE_SCHEMA,
    check_privilege,
)
from pointlessql.types import TableFqn


async def _approve_select_refs(request: Request, refs: list[str]) -> dict[str, str]:
    """Run SELECT enforcement on every reference and return storage map.

    Args:
        request: Incoming FastAPI request — supplies the
            principal-scoped UC client and the auth state.
        refs: 3-part ``catalog.schema.table`` names the SELECT touches.

    Returns:
        Mapping ``full_name → storage_location`` for every ref the
        caller is allowed to read.  Propagates
        :class:`AuthorizationError` raised by :func:`check_privilege`
        when the principal lacks ``SELECT`` on a ref.

    Raises:
        ValidationError: When a ref is not a 3-part name.
        CatalogNotFoundError: When a ref is unknown to soyuz-catalog
            or has no ``storage_location``.
    """
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

    Propagates :class:`ValidationError` raised by
    :meth:`TableFqn.parse` when *target* is malformed, and
    :class:`AuthorizationError` raised by :func:`check_privilege`
    when the principal lacks the required privilege.

    Args:
        request: Incoming FastAPI request.
        target: 3-part UC name that the operation will write to.
        must_exist: When ``True``, raise if the target does not exist.

    Returns:
        ``True`` if the target already exists, ``False`` otherwise.

    Raises:
        CatalogNotFoundError: When *target* is missing and
            ``must_exist`` is ``True``.
    """
    catalog, schema_name, table_name = TableFqn.parse(target).parts()
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
    from pointlessql.pql import prepare_sql, register_delta_view

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
            writes one ``agent_run_operations`` row (forced audit trail).

    Returns:
        A configured :class:`PQL` instance ready for sync dispatch
        from :func:`asyncio.to_thread`.
    """
    from pointlessql.pql import PQL  # noqa: PLC0415 — lazy

    settings: Settings = request.app.state.settings
    return PQL(
        settings=settings,
        principal=principal or None,
        agent_run_id=agent_run_id,
    )
