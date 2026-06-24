"""Delta Sharing management surface: shares, recipients, grants.

Provider-side administration only — recipient-side *reads* speak the
open Delta Sharing protocol directly (bearer token, NDJSON) and live
in :mod:`pointlessql.services.delta_sharing_consumer`.
"""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.add_share_object import AddShareObject
from soyuz_catalog_client.models.create_recipient import CreateRecipient
from soyuz_catalog_client.models.create_share import CreateShare
from soyuz_catalog_client.models.list_recipients_response import ListRecipientsResponse
from soyuz_catalog_client.models.list_shares_response import ListSharesResponse
from soyuz_catalog_client.models.recipient_info import RecipientInfo
from soyuz_catalog_client.models.rotate_recipient_token_response import (
    RotateRecipientTokenResponse,
)
from soyuz_catalog_client.models.share_info import ShareInfo
from soyuz_catalog_client.models.update_recipient import UpdateRecipient
from soyuz_catalog_client.models.update_share import UpdateShare

from pointlessql.services.unitycatalog._api import (
    _add_share_object,
    _create_recipient,
    _create_share,
    _delete_recipient,
    _delete_share,
    _get_recipient,
    _get_share,
    _grant_share,
    _list_recipients,
    _list_shares,
    _remove_share_object,
    _revoke_share,
    _rotate_recipient_token,
    _update_recipient,
    _update_share,
    wrap_catalog_errors,
)


class SharingMixin:
    """Delta Sharing provider administration against soyuz-catalog.

    Covers the provider side of Delta Sharing: shares (named bundles of
    tables), the recipients granted access to them, and the grant /
    revoke edges between the two.

    Every method routes through ``@wrap_catalog_errors``, which normalises
    soyuz-catalog failures into domain exceptions (the shared error
    mapping): a 404 becomes ``CatalogNotFoundError``, other 4xx and
    malformed request bodies become ``ValidationError``, and 5xx /
    transport errors become ``CatalogUnavailableError``.
    """

    _client: Client  # provided by UnityCatalogClient

    # -- Shares --

    @wrap_catalog_errors
    async def list_shares(self) -> list[dict[str, Any]]:
        """Return every share.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Returns:
            One dict per share, or ``[]`` if soyuz returned an
            unexpected response shape.
        """
        response = await _list_shares.asyncio(client=self._client)
        if not isinstance(response, ListSharesResponse):
            return []
        return [share.to_dict() for share in response.shares]

    @wrap_catalog_errors
    async def get_share(self, name: str) -> dict[str, Any]:
        """Return one share, including its objects and grants.

        Failures are normalised by the shared error mapping (see the
        class docstring): an unknown name surfaces as
        ``CatalogNotFoundError``.

        Args:
            name: Share to look up.

        Returns:
            The share's fields as a dict, or ``{}`` if soyuz returned an
            unexpected response shape.
        """
        response = await _get_share.asyncio(name=name, client=self._client)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_share(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a share.

        Failures are normalised by the shared error mapping (see the
        class docstring); a body that ``CreateShare.from_dict`` cannot
        parse surfaces as ``ValidationError``.

        Args:
            data: Request body matching ``CreateShare``.

        Returns:
            The created share as a dict, or ``{}`` if soyuz returned an
            unexpected response shape.
        """
        body = CreateShare.from_dict(data)
        response = await _create_share.asyncio(client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_share(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a share (its comment is the only mutable field).

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to patch.
            patch: Partial body matching ``UpdateShare``.

        Returns:
            The updated share as a dict, or ``{}`` if soyuz returned an
            unexpected response shape.
        """
        body = UpdateShare.from_dict(patch)
        response = await _update_share.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_share(self, name: str) -> None:
        """Delete a share; its objects and grants cascade on soyuz.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to delete.
        """
        await _delete_share.asyncio(name=name, client=self._client)

    @wrap_catalog_errors
    async def add_share_object(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Add a table to a share, optionally re-homed via ``shared_as``.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to add the object to.
            data: Request body matching ``AddShareObject``.

        Returns:
            The updated share as a dict, or ``{}`` if soyuz returned an
            unexpected response shape.
        """
        body = AddShareObject.from_dict(data)
        response = await _add_share_object.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def remove_share_object(self, name: str, table_full_name: str) -> None:
        """Remove a table from a share.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to remove the object from.
            table_full_name: Three-part name of the table to remove.
        """
        await _remove_share_object.asyncio(
            name=name, client=self._client, table_full_name=table_full_name
        )

    @wrap_catalog_errors
    async def grant_share(self, name: str, recipient_name: str) -> None:
        """Grant a recipient access to a share (idempotent PUT).

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to grant access to.
            recipient_name: Recipient receiving access.
        """
        await _grant_share.asyncio(name=name, recipient_name=recipient_name, client=self._client)

    @wrap_catalog_errors
    async def revoke_share(self, name: str, recipient_name: str) -> None:
        """Revoke a recipient's access to a share.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Share to revoke access from.
            recipient_name: Recipient losing access.
        """
        await _revoke_share.asyncio(name=name, recipient_name=recipient_name, client=self._client)

    # -- Recipients --

    @wrap_catalog_errors
    async def list_recipients(self) -> list[dict[str, Any]]:
        """Return every recipient; token hashes are never included.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Returns:
            One dict per recipient, or ``[]`` if soyuz returned an
            unexpected response shape.
        """
        response = await _list_recipients.asyncio(client=self._client)
        if not isinstance(response, ListRecipientsResponse):
            return []
        return [recipient.to_dict() for recipient in response.recipients]

    @wrap_catalog_errors
    async def get_recipient(self, name: str) -> dict[str, Any]:
        """Return one recipient.

        Failures are normalised by the shared error mapping (see the
        class docstring): an unknown name surfaces as
        ``CatalogNotFoundError``.

        Args:
            name: Recipient to look up.

        Returns:
            The recipient's fields as a dict, or ``{}`` if soyuz returned
            an unexpected response shape.
        """
        response = await _get_recipient.asyncio(name=name, client=self._client)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_recipient(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a recipient; the response carries its one-time token.

        The bearer token in the response is shown once and never
        retrievable again. Failures are normalised by the shared error
        mapping (see the class docstring).

        Args:
            data: Request body matching ``CreateRecipient``.

        Returns:
            The created recipient (with its one-time token) as a dict,
            or ``{}`` if soyuz returned an unexpected response shape.
        """
        body = CreateRecipient.from_dict(data)
        response = await _create_recipient.asyncio(client=self._client, body=body)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_recipient(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a recipient (its comment is the only mutable field).

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Recipient to patch.
            patch: Partial body matching ``UpdateRecipient``.

        Returns:
            The updated recipient as a dict, or ``{}`` if soyuz returned
            an unexpected response shape.
        """
        body = UpdateRecipient.from_dict(patch)
        response = await _update_recipient.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_recipient(self, name: str) -> None:
        """Delete a recipient; its grants cascade on soyuz.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            name: Recipient to delete.
        """
        await _delete_recipient.asyncio(name=name, client=self._client)

    @wrap_catalog_errors
    async def rotate_recipient_token(self, name: str) -> dict[str, Any]:
        """Rotate a recipient's bearer token and return the new one.

        Invalidates the old token; the replacement is shown once in the
        response and never retrievable again. Failures are normalised by
        the shared error mapping (see the class docstring).

        Args:
            name: Recipient whose token to rotate.

        Returns:
            The rotation response carrying the new one-time token, or
            ``{}`` if soyuz returned an unexpected response shape.
        """
        response = await _rotate_recipient_token.asyncio(name=name, client=self._client)
        if not isinstance(response, RotateRecipientTokenResponse):
            return {}
        return response.to_dict()
