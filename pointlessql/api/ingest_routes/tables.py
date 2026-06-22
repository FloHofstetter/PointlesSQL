"""table-listing endpoint.

``GET /api/ingest/sources/{id}/tables`` probes the source for its
catalog of available tables.  File-based connectors short-circuit to
a single-row response derived from the configured path; SQL
connectors actually hit ``information_schema.tables`` (Postgres /
MySQL) or ``sqlite_master`` (SQLite) via DuckDB's scanner extensions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import PointlessSQLError, ResourceNotFoundError
from pointlessql.models import IngestSource
from pointlessql.services.ingest._secrets import decrypt_secrets
from pointlessql.services.ingest.probe import ProbeError, list_tables

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "tables"])


@router.get("/api/ingest/sources/{source_id}/tables")
async def api_list_source_tables(request: Request, source_id: int) -> dict[str, Any]:
    """List the tables available on the configured source.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.

    Returns:
        ``{"ok": True, "tables": [name, ...]}`` on success, or
        ``{"ok": False, "reason": str, "hint": str | None}`` when
        the source is unreachable.

    Raises:
        ResourceNotFoundError: When the source doesn't exist or
            belongs to another workspace.
        PointlessSQLError: When the source kind is unsupported.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        try:
            config = json.loads(row.config or "{}")
        except (ValueError, TypeError) as exc:
            raise PointlessSQLError(
                f"source has malformed JSON columns: {exc}",
            ) from exc
        secrets = decrypt_secrets(row.secrets, factory)
        kind = row.kind

    if not isinstance(config, dict):
        config = {}
    typed_config = cast(dict[str, Any], config)

    try:
        names = list_tables(kind, typed_config, secrets)
    except ProbeError as exc:
        return {"ok": False, "reason": exc.reason, "hint": exc.hint}

    return {"ok": True, "tables": [str(n) for n in names]}
