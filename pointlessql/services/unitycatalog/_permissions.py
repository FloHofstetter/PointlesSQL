"""Direct + effective permissions on a securable."""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.get_effective_permissions_api_21_unity_catalog_effective_permissions_securable_type_full_name_get_securable_type import (  # noqa: E501
    GetEffectivePermissionsApi21UnityCatalogEffectivePermissionsSecurableTypeFullNameGetSecurableType,  # noqa: E501
)
from soyuz_catalog_client.models.get_permissions_api_21_unity_catalog_permissions_securable_type_full_name_get_securable_type import (  # noqa: E501
    GetPermissionsApi21UnityCatalogPermissionsSecurableTypeFullNameGetSecurableType,
)
from soyuz_catalog_client.models.permissions_list import PermissionsList
from soyuz_catalog_client.models.update_permissions import UpdatePermissions
from soyuz_catalog_client.models.update_permissions_api_21_unity_catalog_permissions_securable_type_full_name_patch_securable_type import (  # noqa: E501
    UpdatePermissionsApi21UnityCatalogPermissionsSecurableTypeFullNamePatchSecurableType,
)

from pointlessql.services.unitycatalog._api import (
    _get_effective_permissions,
    _get_permissions,
    _update_permissions,
    wrap_catalog_errors,
)


class PermissionsMixin:
    """Direct + effective permission queries and mutations."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def get_permissions(self, securable_type: str, full_name: str) -> list[dict[str, Any]]:
        """Return privilege assignments for a securable.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.

        Returns:
            A list of privilege assignment dicts with ``principal`` and
            ``privileges``.
        """
        st = GetPermissionsApi21UnityCatalogPermissionsSecurableTypeFullNameGetSecurableType(
            securable_type
        )
        response = await _get_permissions.asyncio(
            securable_type=st, full_name=full_name, client=self._client
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]

    @wrap_catalog_errors
    async def get_effective_permissions(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        """Return effective (inherited) permissions for a securable.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.

        Returns:
            A list of effective privilege assignment dicts.
        """
        _EffectiveType = GetEffectivePermissionsApi21UnityCatalogEffectivePermissionsSecurableTypeFullNameGetSecurableType  # noqa: E501, N806
        st = _EffectiveType(securable_type)
        response = await _get_effective_permissions.asyncio(
            securable_type=st, full_name=full_name, client=self._client
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]

    @wrap_catalog_errors
    async def update_permissions(
        self,
        securable_type: str,
        full_name: str,
        changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply permission changes and return updated assignments.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.
            changes: List of ``{"principal": ..., "add": [...], "remove": [...]}``
                dicts.

        Returns:
            The updated privilege assignment list.
        """
        st = UpdatePermissionsApi21UnityCatalogPermissionsSecurableTypeFullNamePatchSecurableType(
            securable_type
        )
        body = UpdatePermissions.from_dict({"changes": changes})
        response = await _update_permissions.asyncio(
            securable_type=st,
            full_name=full_name,
            client=self._client,
            body=body,
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]
