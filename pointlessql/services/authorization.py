"""Authorization enforcement for PointlesSQL.

soyuz-catalog stores permission grants but does not enforce them
(ADR-0005). PointlesSQL is the enforcement layer — this module
checks effective permissions before each operation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import AuthorizationError

if TYPE_CHECKING:
    from pointlessql.services.unitycatalog import UnityCatalogClient

# Privilege constants (space-separated form, matching soyuz-catalog).
USE_CATALOG = "USE CATALOG"
USE_SCHEMA = "USE SCHEMA"
SELECT = "SELECT"
MODIFY = "MODIFY"
MANAGE_GRANTS = "MANAGE_GRANTS"

# Backward-compatible alias — existing code imports AccessDenied from here.
AccessDenied = AuthorizationError


def _user_has_privilege(
    effective: list[dict[str, Any]],
    user_email: str,
    required_privilege: str,
) -> bool:
    """Check whether *user_email* holds *required_privilege* in *effective*.

    Args:
        effective: List of privilege-assignment dicts as returned by
            ``UnityCatalogClient.get_effective_permissions``.
        user_email: The email of the user to check.
        required_privilege: The privilege string to look for.

    Returns:
        ``True`` if the user holds the privilege, ``False`` otherwise.
    """
    for assignment in effective:
        if assignment.get("principal") != user_email:
            continue
        for priv in assignment.get("privileges", []):
            name = priv.get("privilege", priv) if isinstance(priv, dict) else priv
            if name == required_privilege:
                return True
    return False


async def check_privilege(
    uc_client: UnityCatalogClient,
    user_email: str,
    is_admin: bool,
    securable_type: str,
    full_name: str,
    required_privilege: str,
) -> None:
    """Fetch effective permissions and verify the user holds *required_privilege*.

    Admin users always pass.

    Args:
        uc_client: The per-request UC facade.
        user_email: Email of the current user.
        is_admin: Whether the user is an administrator.
        securable_type: One of ``catalog``, ``schema``, ``table``, etc.
        full_name: Dotted name of the securable.
        required_privilege: The privilege that is required.

    Raises:
        AccessDenied: If the user does not hold the privilege.
    """
    if is_admin:
        return

    effective = await uc_client.get_effective_permissions(
        securable_type, full_name
    )
    if not _user_has_privilege(effective, user_email, required_privilege):
        raise AccessDenied(
            user_email, required_privilege, securable_type, full_name
        )


def check_privilege_from_effective(
    effective: list[dict[str, Any]],
    user_email: str,
    is_admin: bool,
    securable_type: str,
    full_name: str,
    required_privilege: str,
) -> None:
    """Check privilege using already-fetched effective permissions.

    Same semantics as :func:`check_privilege` but avoids a duplicate
    HTTP call when the caller already has the effective permissions
    (e.g. detail pages that fetch them for display).

    Args:
        effective: Already-fetched effective permission assignments.
        user_email: Email of the current user.
        is_admin: Whether the user is an administrator.
        securable_type: One of ``catalog``, ``schema``, ``table``, etc.
        full_name: Dotted name of the securable.
        required_privilege: The privilege that is required.

    Raises:
        AccessDenied: If the user does not hold the privilege.
    """
    if is_admin:
        return

    if not _user_has_privilege(effective, user_email, required_privilege):
        raise AccessDenied(
            user_email, required_privilege, securable_type, full_name
        )


def has_privilege(
    effective: list[dict[str, Any]],
    user_email: str,
    is_admin: bool,
    required_privilege: str,
) -> bool:
    """Return whether the user holds a privilege (no exception).

    Useful for computing template flags like ``can_manage``.

    Args:
        effective: Already-fetched effective permission assignments.
        user_email: Email of the current user.
        is_admin: Whether the user is an administrator.
        required_privilege: The privilege to check.

    Returns:
        ``True`` if the user holds the privilege or is admin.
    """
    if is_admin:
        return True
    return _user_has_privilege(effective, user_email, required_privilege)
