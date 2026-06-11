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
    """Delta Sharing provider administration against soyuz-catalog."""

    _client: Client  # provided by UnityCatalogClient

    # -- Shares --

    @wrap_catalog_errors
    async def list_shares(self) -> list[dict[str, Any]]:
        """Return every share."""
        response = await _list_shares.asyncio(client=self._client)
        if not isinstance(response, ListSharesResponse):
            return []
        return [share.to_dict() for share in response.shares]

    @wrap_catalog_errors
    async def get_share(self, name: str) -> dict[str, Any]:
        """Return one share (objects + grants included)."""
        response = await _get_share.asyncio(name=name, client=self._client)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_share(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a share."""
        body = CreateShare.from_dict(data)
        response = await _create_share.asyncio(client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_share(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a share's comment."""
        body = UpdateShare.from_dict(patch)
        response = await _update_share.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_share(self, name: str) -> None:
        """Delete a share (objects + grants cascade on soyuz)."""
        await _delete_share.asyncio(name=name, client=self._client)

    @wrap_catalog_errors
    async def add_share_object(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Add a table to a share (optionally re-homed via ``shared_as``)."""
        body = AddShareObject.from_dict(data)
        response = await _add_share_object.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ShareInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def remove_share_object(self, name: str, table_full_name: str) -> None:
        """Remove a table from a share."""
        await _remove_share_object.asyncio(
            name=name, client=self._client, table_full_name=table_full_name
        )

    @wrap_catalog_errors
    async def grant_share(self, name: str, recipient_name: str) -> None:
        """Grant a recipient access to a share (idempotent PUT)."""
        await _grant_share.asyncio(name=name, recipient_name=recipient_name, client=self._client)

    @wrap_catalog_errors
    async def revoke_share(self, name: str, recipient_name: str) -> None:
        """Revoke a recipient's access to a share."""
        await _revoke_share.asyncio(name=name, recipient_name=recipient_name, client=self._client)

    # -- Recipients --

    @wrap_catalog_errors
    async def list_recipients(self) -> list[dict[str, Any]]:
        """Return every recipient (token hashes never ship)."""
        response = await _list_recipients.asyncio(client=self._client)
        if not isinstance(response, ListRecipientsResponse):
            return []
        return [recipient.to_dict() for recipient in response.recipients]

    @wrap_catalog_errors
    async def get_recipient(self, name: str) -> dict[str, Any]:
        """Return one recipient."""
        response = await _get_recipient.asyncio(name=name, client=self._client)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_recipient(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a recipient — the response carries the one-time token."""
        body = CreateRecipient.from_dict(data)
        response = await _create_recipient.asyncio(client=self._client, body=body)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_recipient(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a recipient's comment."""
        body = UpdateRecipient.from_dict(patch)
        response = await _update_recipient.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, RecipientInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_recipient(self, name: str) -> None:
        """Delete a recipient (grants cascade on soyuz)."""
        await _delete_recipient.asyncio(name=name, client=self._client)

    @wrap_catalog_errors
    async def rotate_recipient_token(self, name: str) -> dict[str, Any]:
        """Rotate a recipient's bearer token; returns the new one-time token."""
        response = await _rotate_recipient_token.asyncio(name=name, client=self._client)
        if not isinstance(response, RotateRecipientTokenResponse):
            return {}
        return response.to_dict()
