"""SQL-cell support helpers for the Phase-66.5 browser notebook editor.

A SQL cell is a regular code cell whose marker carries the ``[sql]``
tag (e.g. ``# %% [sql] df``).  Execution goes through the kernel —
the cell source is wrapped server-side into a call to the kernel-
bootstrap helper :func:`__pql_sql_run` so the resulting pandas
DataFrame is bound to the user-named variable and inline-displayed.

This module owns:

* :func:`build_kernel_wrapper` — turn raw SQL + approved-table map
  + result-var into the Python snippet the WebSocket handler hands
  the kernel.
* :func:`resolve_approved_tables` — UC privilege check + storage-
  location lookup for every table referenced by the SQL.

Both are kept tiny and free of route-layer dependencies so the WS
handler can reuse them without dragging the ``DispatchContext``
machinery the SQL editor lives in.
"""

from __future__ import annotations

from typing import Any

from pointlessql.exceptions import (
    AuthorizationError,
    CatalogNotFoundError,
    ValidationError,
)
from pointlessql.pql import SQLParseError, prepare_sql

_DEFAULT_RESULT_VAR = "df"
_VALID_RESULT_VAR = (
    # ASCII identifier — A-Za-z_ followed by A-Za-z0-9_ (matches
    # the marker grammar's positional segment).
    "[A-Za-z_][A-Za-z0-9_]*"
)


def build_kernel_wrapper(
    sql_source: str,
    *,
    approved_tables: dict[str, str],
    result_var: str | None,
    max_rows: int = 1000,
    table_policies: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Return the Python snippet that runs ``sql_source`` in the kernel.

    The snippet calls the kernel-side ``__pql_sql_run(...)`` helper
    (defined by :data:`KernelSession._NOTEBOOK_BOOTSTRAP_CODE`).  The
    helper materialises the result as pandas, binds it to ``result_var``
    in the kernel namespace, and displays it inline so the existing
    iopub → output_renderer.js path renders the table without further
    wiring.

    Args:
        sql_source: Raw SQL the user typed in the cell.
        approved_tables: Mapping ``full_name → storage_location`` —
            already gated by the route layer.
        result_var: Optional Python identifier the user named after
            the ``[sql]`` tag.  Defaults to ``"df"``.
        max_rows: Per-query row cap for the kernel's ``PQL.sql``
            call.  Mirrors the SQL editor default.
        table_policies: Optional ``full_name → policy-dict`` map of
            row-filter / column-mask policies (the plain-dict form of
            :class:`pointlessql.pql._policies.TablePolicy` so it
            survives the ``repr`` transfer into the kernel).

    Returns:
        A multi-line Python source string suitable for kernel
        execution.  Idempotent for the same inputs.
    """
    var = (result_var or _DEFAULT_RESULT_VAR).strip()
    # Defence-in-depth: the marker grammar already restricts the
    # positional segment, but the result_var can also arrive via the
    # WS execute frame from the browser.  Drop any value that does not
    # match the same identifier shape so a malicious payload cannot
    # smuggle Python into the snippet.
    import re

    if not re.fullmatch(_VALID_RESULT_VAR, var):
        var = _DEFAULT_RESULT_VAR
    # repr() is the Python-source-safe escape — it handles quotes,
    # backslashes, multi-line strings, and unicode.  The kernel sees
    # the SQL verbatim once unwrapped.
    sql_literal = repr(sql_source)
    approved_literal = repr(approved_tables)
    policies_literal = repr(table_policies or {})
    return (
        f"__pql_sql_run({sql_literal}, "
        f"approved_tables={approved_literal}, "
        f"result_var={var!r}, max_rows={int(max_rows)}, "
        f"table_policies={policies_literal})\n"
    )


async def resolve_approved_tables(
    sql_source: str,
    *,
    uc_client: Any,
    actor_email: str,
    is_admin: bool,
) -> dict[str, str]:
    """Return ``full_name → storage_location`` for every ref in ``sql_source``.

    Mirrors :func:`pointlessql.api.sql._dispatcher._enforce_select_per_table`
    but takes its dependencies as plain arguments so the WebSocket
    handler can reuse it without constructing a ``DispatchContext``.
    Thin wrapper over :func:`resolve_select_context` — every error
    (``SQLParseError``, ``CatalogNotFoundError``,
    ``AuthorizationError``) propagates from there unchanged.

    Args:
        sql_source: Raw SQL the user typed.  Must parse via
            :func:`prepare_sql` and reference 3-part-qualified
            tables only.
        uc_client: A :class:`UnityCatalogClient` instance — typically
            ``request.app.state.uc_client``.
        actor_email: The principal whose privileges are being
            checked (the cookie user's email).
        is_admin: ``True`` when the actor holds the global admin role
            so :func:`check_privilege` can short-circuit.

    Returns:
        Mapping ``full_name → storage_location`` for every parsed ref.
    """
    approved, _policies = await resolve_select_context(
        sql_source, uc_client=uc_client, actor_email=actor_email, is_admin=is_admin
    )
    return approved


async def resolve_select_context(
    sql_source: str,
    *,
    uc_client: Any,
    actor_email: str,
    is_admin: bool,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """SELECT enforcement plus effective read-policy collection.

    Same handshake as :func:`resolve_approved_tables`, but the table
    info fetched for the storage lookup also yields each table's
    row-filter / column-mask policy as a plain dict (the ``repr``-
    transferable form kernels need).  Admins and the table owner are
    exempt.

    Args:
        sql_source: Raw SQL the user typed.
        uc_client: A :class:`UnityCatalogClient` instance.
        actor_email: The principal whose privileges are checked.
        is_admin: Whether the actor short-circuits privilege checks
            (and policy collection).

    Returns:
        ``(approved, policies)`` — the storage map plus
        ``full_name → policy-dict`` for every governed ref.

    Raises:
        SQLParseError: When ``sql_source`` does not parse as a
            single SELECT, or a parsed ref is not 3-part-qualified.
        CatalogNotFoundError: When a referenced table is unknown
            or has no storage_location on soyuz-catalog.
        ValidationError: When a stored policy property is malformed.
    """
    from dataclasses import asdict

    from pointlessql.pql._policies import extract_table_policy
    from pointlessql.services.authorization import SELECT, check_privilege

    prepared = prepare_sql(sql_source)
    approved: dict[str, str] = {}
    policies: dict[str, dict[str, Any]] = {}
    for full_name in prepared.refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            raise SQLParseError(
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
        # check_privilege raises AuthorizationError on miss.
        await check_privilege(uc_client, actor_email, is_admin, "table", full_name, SELECT)
        # AuthorizationError is the documented raise from
        # check_privilege; keep this no-op assignment so the
        # surface stays explicit.
        _ = AuthorizationError  # noqa: F841
        approved[full_name] = storage
        is_owner = bool(actor_email) and info.get("owner") == actor_email
        if not is_admin and not is_owner:
            try:
                policy = extract_table_policy(info, principal=actor_email)
            except ValueError as exc:
                raise ValidationError(
                    f"table {full_name!r} carries a malformed read policy: {exc}"
                ) from exc
            if policy is not None:
                policies[full_name] = asdict(policy)
    return approved, policies
