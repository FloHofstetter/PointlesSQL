"""Phase 82.5 — Health-band feed for a DP's ingest sources.

``GET /api/data-products/{catalog}/{schema}/ingest-status`` returns
every IngestSource whose ``table_mappings[*].target_fqn`` lands a
table inside the DP's catalog+schema, with its latest pull stats.
The DP detail page renders these inline in the Health hero so
consumers see "where does this data come from + when was it last
refreshed" without leaving the page.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DataProduct, IngestSource

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-products", "ingest-status"])


@router.get("/api/data-products/{catalog}/{schema}/ingest-status")
async def api_dp_ingest_status(
    request: Request, catalog: str, schema: str
) -> dict[str, Any]:
    """List ingest sources feeding the DP's catalog.schema.

    Args:
        request: Incoming FastAPI request.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        ``{"sources": [{name, kind, target_fqn, last_pull_ts,
        last_pull_ok, cron_expr}, ...]}``.  Empty list when no
        ingest source targets this DP.

    Raises:
        ResourceNotFoundError: When the DP doesn't exist in the
            caller's workspace.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    target_prefix = f"{catalog}.{schema}."
    with factory() as session:
        dp = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        ).scalar_one_or_none()
        if dp is None:
            raise ResourceNotFoundError("data product not found")
        rows = list(
            session.scalars(
                select(IngestSource).where(
                    IngestSource.workspace_id == workspace_id,
                    IngestSource.is_active.is_(True),
                )
            ).all()
        )

    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            mappings_raw = json.loads(row.table_mappings or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(mappings_raw, list):
            continue
        mappings: list[dict[str, Any]] = [
            m for m in cast(list[Any], mappings_raw) if isinstance(m, dict)
        ]
        for m in mappings:
            target_fqn = str(m.get("target_fqn") or "")
            if not target_fqn.startswith(target_prefix):
                continue
            stats_raw: object = m.get("last_pull_stats") or {}
            stats: dict[str, Any] = (
                cast(dict[str, Any], stats_raw)
                if isinstance(stats_raw, dict)
                else {}
            )
            out.append(
                {
                    "source_id": int(row.id),
                    "source_name": row.name,
                    "kind": row.kind,
                    "target_fqn": target_fqn,
                    "last_pull_ts": stats.get("ts"),
                    "last_pull_ok": stats.get("ok"),
                    "last_pull_rows": stats.get("rows_written"),
                }
            )
    return {"sources": out}
