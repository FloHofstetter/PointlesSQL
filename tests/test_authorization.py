"""Unit tests for the authorization enforcement service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    MODIFY,
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    AccessDenied,
    check_privilege,
    check_privilege_from_effective,
    has_privilege,
)

# -- Fixtures and helpers --


def _effective(principal: str, privileges: list[str]) -> list[dict]:
    """Build effective permissions data matching soyuz-catalog format."""
    return [{"principal": principal, "privileges": privileges}]


def _multi_effective(*entries: tuple[str, list[str]]) -> list[dict]:
    return [{"principal": p, "privileges": privs} for p, privs in entries]


# -- check_privilege (async, makes HTTP call) --


class TestCheckPrivilege:
    async def test_admin_always_passes(self) -> None:
        """Admin users bypass all checks without making any HTTP call."""
        uc = MagicMock()
        uc.get_effective_permissions = AsyncMock()
        await check_privilege(uc, "admin@test.com", True, "catalog", "my_cat", USE_CATALOG)
        uc.get_effective_permissions.assert_not_called()

    async def test_user_with_privilege_passes(self) -> None:
        uc = MagicMock()
        uc.get_effective_permissions = AsyncMock(
            return_value=_effective("user@test.com", [USE_CATALOG])
        )
        await check_privilege(uc, "user@test.com", False, "catalog", "my_cat", USE_CATALOG)

    async def test_user_without_privilege_denied(self) -> None:
        uc = MagicMock()
        uc.get_effective_permissions = AsyncMock(return_value=_effective("user@test.com", [SELECT]))
        with pytest.raises(AccessDenied) as exc_info:
            await check_privilege(uc, "user@test.com", False, "catalog", "my_cat", USE_CATALOG)
        assert exc_info.value.privilege == USE_CATALOG
        assert exc_info.value.principal == "user@test.com"
        assert exc_info.value.securable_type == "catalog"
        assert exc_info.value.full_name == "my_cat"

    async def test_user_not_in_assignments_denied(self) -> None:
        uc = MagicMock()
        uc.get_effective_permissions = AsyncMock(
            return_value=_effective("other@test.com", [USE_CATALOG])
        )
        with pytest.raises(AccessDenied):
            await check_privilege(uc, "user@test.com", False, "catalog", "my_cat", USE_CATALOG)

    async def test_empty_effective_permissions_denied(self) -> None:
        uc = MagicMock()
        uc.get_effective_permissions = AsyncMock(return_value=[])
        with pytest.raises(AccessDenied):
            await check_privilege(uc, "user@test.com", False, "catalog", "my_cat", USE_CATALOG)


# -- check_privilege_from_effective (sync, uses existing data) --


class TestCheckPrivilegeFromEffective:
    def test_admin_passes(self) -> None:
        check_privilege_from_effective([], "admin@test.com", True, "catalog", "my_cat", USE_CATALOG)

    def test_user_with_privilege_passes(self) -> None:
        effective = _effective("user@test.com", [USE_SCHEMA, MODIFY])
        check_privilege_from_effective(
            effective, "user@test.com", False, "schema", "cat.sch", USE_SCHEMA
        )

    def test_user_without_privilege_denied(self) -> None:
        effective = _effective("user@test.com", [SELECT])
        with pytest.raises(AccessDenied):
            check_privilege_from_effective(
                effective, "user@test.com", False, "catalog", "my_cat", MODIFY
            )

    def test_dict_privilege_format(self) -> None:
        """Privileges may be dicts with a ``privilege`` key."""
        effective = [
            {
                "principal": "user@test.com",
                "privileges": [{"privilege": USE_CATALOG}],
            }
        ]
        check_privilege_from_effective(
            effective, "user@test.com", False, "catalog", "my_cat", USE_CATALOG
        )

    def test_multiple_principals(self) -> None:
        effective = _multi_effective(
            ("other@test.com", [USE_CATALOG]),
            ("user@test.com", [SELECT]),
        )
        with pytest.raises(AccessDenied):
            check_privilege_from_effective(
                effective, "user@test.com", False, "catalog", "my_cat", USE_CATALOG
            )

    def test_manage_grants(self) -> None:
        effective = _effective("user@test.com", [MANAGE_GRANTS])
        check_privilege_from_effective(
            effective, "user@test.com", False, "catalog", "my_cat", MANAGE_GRANTS
        )


# -- has_privilege (bool, no exception) --


class TestHasPrivilege:
    def test_admin_always_true(self) -> None:
        assert has_privilege([], "admin@test.com", True, MANAGE_GRANTS) is True

    def test_user_with_privilege(self) -> None:
        effective = _effective("user@test.com", [SELECT, MODIFY])
        assert has_privilege(effective, "user@test.com", False, MODIFY) is True

    def test_user_without_privilege(self) -> None:
        effective = _effective("user@test.com", [SELECT])
        assert has_privilege(effective, "user@test.com", False, MANAGE_GRANTS) is False

    def test_empty_is_false(self) -> None:
        assert has_privilege([], "user@test.com", False, SELECT) is False
