"""Shared helpers for the governance sub-routers.

* :func:`split_full_name` parses a ``cat.sch.tbl`` UC name into the
  triple components every endpoint validates against.
* :func:`enforce_table_profile_access` collapses the SELECT-or-admin
  check used by profile + stats GET into one helper.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services.authorization import SELECT, check_privilege


def split_full_name(full_name: str) -> tuple[str, str, str]:
    """Split a UC three-part name, raising on bad shape.

    Args:
        full_name: Dotted identifier ``catalog.schema.table``.

    Returns:
        Tuple ``(catalog, schema, table)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.table, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]


async def enforce_table_profile_access(
    request: Request,
    full_name: str,
) -> dict[str, Any]:
    """Resolve table info and check that the caller may profile it.

    Admin short-circuits SELECT enforcement; every other caller must
    hold SELECT on the table before they can trigger a profile run.

    Args:
        request: Incoming request.
        full_name: Three-part UC name.

    Returns:
        The UC ``table_info`` dict.

    Raises:
        CatalogNotFoundError: When the table is missing or has no
            ``storage_location``.
        AuthorizationError: When the caller lacks SELECT on the table.
    """  # noqa: DOC502,DOC503 — raised via await below
    from pointlessql.exceptions import CatalogNotFoundError

    client = get_uc_client(request)
    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    is_admin = bool(user.get("is_admin", False))
    catalog, schema, table = split_full_name(full_name)
    table_info = await client.get_table(catalog, schema, table)
    if not table_info:
        raise CatalogNotFoundError(f"Table {full_name!r} not found.")
    storage_location = table_info.get("storage_location")
    if not isinstance(storage_location, str) or not storage_location:
        raise CatalogNotFoundError(
            f"Table {full_name!r} has no storage_location on soyuz-catalog.",
        )
    await check_privilege(client, email, is_admin, "table", full_name, SELECT)
    return table_info
