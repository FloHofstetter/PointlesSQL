"""Per-table SELECT and per-target MODIFY enforcement.

Both helpers are called by every write branch and by the legacy
EXPLAIN path in :mod:`pointlessql.api.sql.editor`.  Kept in their own
module so adding a new write branch never has to copy the
storage_location / privilege handshake.
"""

from __future__ import annotations

from typing import Any

from pointlessql.api.dependencies import get_uc_client
from pointlessql.api.sql._dispatcher._types import DispatchContext
from pointlessql.exceptions import (
    CatalogNotFoundError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.services.authorization import MODIFY, SELECT, USE_SCHEMA, check_privilege


async def enforce_select_per_table(ctx: DispatchContext, refs: list[str]) -> dict[str, str]:
    """Run ``SELECT`` enforcement on every ref and return storage map.

    Propagates :class:`AuthorizationError` raised by
    :func:`check_privilege` when the caller lacks ``SELECT`` on a
    referenced table.

    Args:
        ctx: Dispatcher context.
        refs: 3-part table names to enforce.

    Returns:
        Mapping ``full_name → storage_location`` for every ref.
    """
    approved, _policies = await enforce_select_with_policies(ctx, refs)
    return approved


async def enforce_select_with_policies(
    ctx: DispatchContext, refs: list[str]
) -> tuple[dict[str, str], dict[str, Any]]:
    """SELECT enforcement plus effective read-policy collection.

    Same handshake as :func:`enforce_select_per_table`, but the
    table info fetched for the storage lookup also yields each
    table's row-filter / column-mask policy
    (:func:`pointlessql.pql._policies.extract_table_policy`).
    Admins and the table owner are exempt — they administer the
    policy, so their reads stay raw.

    Args:
        ctx: Dispatcher context.
        refs: 3-part table names to enforce.

    Returns:
        ``(approved, policies)`` — the storage map plus
        ``full_name → TablePolicy`` for every governed ref.

    Raises:
        SQLExecutionError: When a ref is not 3-part qualified.
        CatalogNotFoundError: When a ref is unknown.
        ValidationError: When a stored policy property is malformed.
    """
    from pointlessql.pql._policies import extract_table_policy

    uc_client = get_uc_client(ctx.request)
    approved: dict[str, str] = {}
    policies: dict[str, Any] = {}
    for full_name in refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            raise SQLExecutionError(
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
        await check_privilege(uc_client, ctx.actor_email, ctx.is_admin, "table", full_name, SELECT)
        approved[full_name] = storage
        is_owner = bool(ctx.actor_email) and info.get("owner") == ctx.actor_email
        if not ctx.is_admin and not is_owner:
            try:
                policy = extract_table_policy(info, principal=ctx.actor_email)
            except ValueError as exc:
                raise ValidationError(
                    f"table {full_name!r} carries a malformed read policy: {exc}"
                ) from exc
            if policy is not None:
                policies[full_name] = policy
    return approved, policies


async def enforce_modify_target(ctx: DispatchContext, target: str, *, must_exist: bool) -> bool:
    """Enforce write privilege on *target* and report whether it exists.

    Mirrors :func:`pointlessql.api.pql_write_routes._check_write_target`
    so editor and Hermes-plugin write paths agree on the gate.
    Propagates :class:`AuthorizationError` raised by
    :func:`check_privilege` when the caller lacks the required gate
    (``MODIFY`` on an existing target, ``USE_SCHEMA`` on the parent
    of a new one).

    Args:
        ctx: Dispatcher context.
        target: 3-part UC name.
        must_exist: When ``True``, raise if the target does not exist.

    Returns:
        ``True`` if the target already exists, ``False`` otherwise.

    Raises:
        ValidationError: When *target* is not 3-part.
        CatalogNotFoundError: When ``must_exist=True`` and target absent.
    """
    parts = target.split(".")
    if len(parts) != 3:
        raise ValidationError(
            f"Internal error: expected 3-part name, got {target!r}.",
        )
    uc_client = get_uc_client(ctx.request)
    info = await uc_client.get_table(parts[0], parts[1], parts[2])
    if not info:
        if must_exist:
            raise CatalogNotFoundError(f"Table not found: {target!r}")
        # New-target path requires USE_SCHEMA on the parent so the
        # caller has permission to create children underneath.
        parent_schema = f"{parts[0]}.{parts[1]}"
        await check_privilege(
            uc_client, ctx.actor_email, ctx.is_admin, "schema", parent_schema, USE_SCHEMA
        )
        return False
    await check_privilege(uc_client, ctx.actor_email, ctx.is_admin, "table", target, MODIFY)
    return True
