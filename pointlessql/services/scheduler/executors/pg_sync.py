# pyright: reportUnusedFunction=false
"""``pg_sync`` job kind — calls :func:`pg_sync.run_sync` for a foreign catalog.

Cross-module imports stay function-local to dodge the circular chain
through :mod:`pointlessql.db` and :mod:`pointlessql.models`.
"""

from __future__ import annotations

import logging
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _pg_sync_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute the ``pg_sync`` kind by calling ``pg_sync.run_sync``.

    Resolves the catalog's connection and (optional) credential through
    the principal-forwarded ``uc_client`` so the scheduler inherits the
    same authorization path the manual "Sync now" route uses.

    Args:
        job_run_id: Current run id (unused here but part of the
            :data:`JobExecutor` signature).
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``catalog_name``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``catalog_name`` is missing from config
            or the catalog is not a foreign catalog.
    """
    del job_run_id, user_info  # unused but part of executor signature

    catalog_name = config.get("catalog_name")
    if not catalog_name:
        raise ValidationError("pg_sync job config is missing required key 'catalog_name'")

    from pointlessql.db import get_session_factory
    from pointlessql.services import pg_sync as pg_sync_service

    catalog = await uc_client.get_catalog(str(catalog_name))
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise ValidationError(f"pg_sync job target '{catalog_name}' is not a foreign catalog")
    connection = await uc_client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = options.get("credential_name") if isinstance(options, dict) else None
    if credential_name:
        credential = await uc_client.get_credential(str(credential_name))

    factory = get_session_factory()
    await pg_sync_service.run_sync(
        uc=uc_client,
        factory=factory,
        catalog_name=str(catalog_name),
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )
