"""Generated soyuz-catalog client function imports + error decorator.

Single import surface for every typed function the mixins call.
Re-exported from :mod:`pointlessql.services.unitycatalog` so existing
tests that monkeypatch
``pointlessql.services.unitycatalog._get_tags.asyncio`` keep finding
the same module object.

The :func:`_wrap_catalog_errors` decorator lives here (rather than on
each mixin) so its mapping of ``UnexpectedStatus`` /
``httpx.HTTPError`` / ``KeyError|TypeError`` → domain exceptions stays
consistent across every API surface.
"""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from soyuz_catalog_client.api.catalogs import (
    create_catalog_api_2_1_unity_catalog_catalogs_post as _create_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    delete_catalog_api_2_1_unity_catalog_catalogs_name_delete as _delete_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    get_catalog_api_2_1_unity_catalog_catalogs_name_get as _get_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    list_catalogs_api_2_1_unity_catalog_catalogs_get as _list_catalogs,
)
from soyuz_catalog_client.api.catalogs import (
    update_catalog_api_2_1_unity_catalog_catalogs_name_patch as _update_catalog,
)
from soyuz_catalog_client.api.connections import (
    create_connection_api_2_1_unity_catalog_connections_post as _create_connection,
)
from soyuz_catalog_client.api.connections import (
    delete_connection_api_2_1_unity_catalog_connections_name_delete as _delete_connection,
)
from soyuz_catalog_client.api.connections import (
    get_connection_api_2_1_unity_catalog_connections_name_get as _get_connection,
)
from soyuz_catalog_client.api.connections import (
    list_connections_api_2_1_unity_catalog_connections_get as _list_connections,
)
from soyuz_catalog_client.api.connections import (
    update_connection_api_2_1_unity_catalog_connections_name_patch as _update_connection,
)
from soyuz_catalog_client.api.credentials import (
    create_credential_api_2_1_unity_catalog_credentials_post as _create_credential,
)
from soyuz_catalog_client.api.credentials import (
    delete_credential_api_2_1_unity_catalog_credentials_name_delete as _delete_credential,
)
from soyuz_catalog_client.api.credentials import (
    get_credential_api_2_1_unity_catalog_credentials_name_get as _get_credential,
)
from soyuz_catalog_client.api.credentials import (
    list_credentials_api_2_1_unity_catalog_credentials_get as _list_credentials,
)
from soyuz_catalog_client.api.credentials import (
    update_credential_api_2_1_unity_catalog_credentials_name_patch as _update_credential,
)
from soyuz_catalog_client.api.effective_permissions import (
    get_effective_permissions_api_2_1_unity_catalog_effective_permissions_securable_type_full_name_get as _get_effective_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.external_locations import (
    create_external_location_api_2_1_unity_catalog_external_locations_post as _create_ext_loc,
)
from soyuz_catalog_client.api.external_locations import (
    delete_external_location_api_2_1_unity_catalog_external_locations_name_delete as _delete_ext_loc,  # noqa: E501
)
from soyuz_catalog_client.api.external_locations import (
    get_external_location_api_2_1_unity_catalog_external_locations_name_get as _get_ext_loc,
)
from soyuz_catalog_client.api.external_locations import (
    list_external_locations_api_2_1_unity_catalog_external_locations_get as _list_ext_locs,
)
from soyuz_catalog_client.api.external_locations import (
    update_external_location_api_2_1_unity_catalog_external_locations_name_patch as _update_ext_loc,
)
from soyuz_catalog_client.api.lineage import (
    get_downstream_lineage_downstream_full_name_get as _get_downstream,
)
from soyuz_catalog_client.api.lineage import (
    get_upstream_lineage_upstream_full_name_get as _get_upstream,
)
from soyuz_catalog_client.api.permissions import (
    get_permissions_api_2_1_unity_catalog_permissions_securable_type_full_name_get as _get_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.permissions import (
    update_permissions_api_2_1_unity_catalog_permissions_securable_type_full_name_patch as _update_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.schemas import (
    create_schema_api_2_1_unity_catalog_schemas_post as _create_schema,
)
from soyuz_catalog_client.api.schemas import (
    delete_schema_api_2_1_unity_catalog_schemas_full_name_delete as _delete_schema,
)
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.schemas import (
    list_schemas_api_2_1_unity_catalog_schemas_get as _list_schemas,
)
from soyuz_catalog_client.api.schemas import (
    update_schema_api_2_1_unity_catalog_schemas_full_name_patch as _update_schema,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    delete_table_api_2_1_unity_catalog_tables_full_name_delete as _delete_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.api.tags import (
    get_tags_tags_securable_type_full_name_get as _get_tags,
)
from soyuz_catalog_client.api.tags import (
    update_tags_tags_securable_type_full_name_patch as _update_tags,
)
from soyuz_catalog_client.errors import UnexpectedStatus

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)

logger = logging.getLogger(__name__)


__all__ = [
    "_create_catalog",
    "_create_connection",
    "_create_credential",
    "_create_ext_loc",
    "_create_schema",
    "_create_table",
    "_delete_catalog",
    "_delete_connection",
    "_delete_credential",
    "_delete_ext_loc",
    "_delete_schema",
    "_delete_table",
    "_get_catalog",
    "_get_connection",
    "_get_credential",
    "_get_downstream",
    "_get_effective_permissions",
    "_get_ext_loc",
    "_get_permissions",
    "_get_schema",
    "_get_table",
    "_get_tags",
    "_get_upstream",
    "_list_catalogs",
    "_list_connections",
    "_list_credentials",
    "_list_ext_locs",
    "_list_schemas",
    "_update_catalog",
    "_update_connection",
    "_update_credential",
    "_update_ext_loc",
    "_update_permissions",
    "_update_schema",
    "_update_tags",
    "wrap_catalog_errors",
]


def _friendly_soyuz_message(exc: UnexpectedStatus) -> str:
    r"""Extract the human-readable ``message`` field from a soyuz error body.

    Soyuz's error envelope is consistent: ``{"error_code": "NOT_FOUND",
    "message": "Catalog 'phase157' does not exist", "request_id": "…"}``.
    Surfacing only ``message`` gives the SQL-editor and other UI
    surfaces a one-line error instead of the multi-line
    ``"Unexpected status code: 404\n\nResponse content: {…raw JSON…}"``
    that the generated client's ``__str__`` produces.

    Falls back to the raw ``str(exc)`` if the body is not parseable
    JSON or lacks a ``message`` — better verbose than empty.
    """
    try:
        body = json.loads(exc.content.decode(errors="ignore"))
    except (ValueError, AttributeError):
        return str(exc)
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return str(exc)


def wrap_catalog_errors[T](
    fn: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wrap an async method so transport + client errors become domain exceptions.

    Mapping (BUG-22-01 + BUG-22-02):

    - soyuz 4xx responses surface as ``ValidationError`` (422) or
      ``CatalogNotFoundError`` (404) depending on the exact status,
      because they describe *user input* that soyuz rejected, not an
      unreachable catalog server.  The wrapped exception carries the
      ``message`` field from soyuz's JSON envelope (see
      :func:`_friendly_soyuz_message`) so the SQL editor and other
      UI surfaces don't show the raw ``UnexpectedStatus`` dump.
    - soyuz 5xx responses and transport errors (httpx timeouts,
      connection refused, etc.) stay ``CatalogUnavailableError`` (502).
    - ``KeyError`` / ``TypeError`` raised by a generated
      ``Create*.from_dict()`` call (missing required request field)
      surface as ``ValidationError`` — the old behaviour leaked a
      bare ``KeyError`` as HTTP 500.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await fn(*args, **kwargs)
        except UnexpectedStatus as exc:
            logger.warning("soyuz-catalog request failed in %s", fn.__name__, exc_info=True)
            code = exc.status_code
            detail = _friendly_soyuz_message(exc)
            if code == 404:
                raise CatalogNotFoundError(detail) from exc
            if 400 <= code < 500:
                raise ValidationError(detail) from exc
            raise CatalogUnavailableError(f"Catalog server unavailable: {detail}") from exc
        except httpx.HTTPError as exc:
            logger.warning("soyuz-catalog transport failed in %s", fn.__name__, exc_info=True)
            raise CatalogUnavailableError(f"Catalog server unavailable: {exc}") from exc
        except (KeyError, TypeError) as exc:
            # Generated ``Create*.from_dict()`` raises these when a
            # required request-body field is missing or the wrong type.
            # That is user input, not a server failure — surface it as
            # a validation error rather than a 500.
            logger.warning(
                "soyuz-catalog body validation failed in %s",
                fn.__name__,
                exc_info=True,
            )
            raise ValidationError(f"Invalid request body: {exc}") from exc

    return wrapper
