"""Phase 84.2 — release stream per DataProduct version.

* ``GET /api/data-products/{c}/{s}/releases`` — JSON list of every
  detected version bump, newest first.
* ``GET /api/data-products/{c}/{s}/releases.atom`` — RSS-style
  Atom feed so CI / RSS readers can subscribe.

Releases are emitted by the YAML loader whenever it sees a new
``DataProduct.contract_yaml_hash`` or a new ``version`` string.
The history grows monotonically; downgrades are also recorded.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import desc, select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DataProduct, DataProductRelease

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-products", "releases"])


def _resolve_dp(
    request: Request, catalog: str, schema: str
) -> DataProduct:
    """Resolve the workspace-scoped DataProduct row or 404."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
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
        session.expunge(dp)
    return dp


def _load_releases(
    request: Request, dp_id: int, limit: int = 100
) -> list[DataProductRelease]:
    """Return the last *limit* releases for *dp_id*, newest first."""
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(DataProductRelease)
                .where(DataProductRelease.data_product_id == dp_id)
                .order_by(desc(DataProductRelease.released_at))
                .limit(limit)
            ).all()
        )
        for r in rows:
            session.expunge(r)
    return rows


@router.get("/api/data-products/{catalog}/{schema}/releases")
async def api_dp_releases(
    request: Request, catalog: str, schema: str
) -> dict[str, Any]:
    """List recorded releases for a DataProduct.

    Args:
        request: Incoming request.
        catalog: UC catalog.
        schema: UC schema.

    Returns:
        ``{"releases": [...]}`` newest-first.
    """
    dp = _resolve_dp(request, catalog, schema)
    rows = _load_releases(request, int(dp.id))
    return {
        "releases": [
            {
                "id": int(r.id),
                "version": r.version,
                "contract_yaml_hash": r.contract_yaml_hash,
                "released_at": r.released_at.isoformat()
                if r.released_at
                else None,
                "notes_md": r.notes_md,
                "signed_off_by_email": r.signed_off_by_email or None,
            }
            for r in rows
        ]
    }


@router.get("/api/data-products/{catalog}/{schema}/releases.atom")
async def api_dp_releases_atom(
    request: Request, catalog: str, schema: str
) -> Response:
    """Atom feed of recorded releases.

    Args:
        request: Incoming request.
        catalog: UC catalog.
        schema: UC schema.

    Returns:
        XML Atom feed (``application/atom+xml``).
    """
    dp = _resolve_dp(request, catalog, schema)
    rows = _load_releases(request, int(dp.id))
    base_url = str(request.url).rsplit("/releases.atom", 1)[0]
    feed_id = f"urn:pointlessql:dp:{catalog}.{schema}:releases"
    updated = (
        rows[0].released_at.isoformat()
        if rows
        else datetime.datetime.now(datetime.UTC).isoformat()
    )
    title = f"{catalog}.{schema} releases"
    entries: list[str] = []
    for r in rows:
        published = r.released_at.isoformat() if r.released_at else ""
        body = (
            f"Version {r.version}\n"
            f"Hash {r.contract_yaml_hash}\n"
            f"Signed off by: {r.signed_off_by_email or '—'}\n"
        )
        entries.append(
            f"  <entry>\n"
            f"    <id>{escape(feed_id)}:{r.id}</id>\n"
            f"    <title>v{escape(r.version)}</title>\n"
            f"    <updated>{escape(published)}</updated>\n"
            f"    <published>{escape(published)}</published>\n"
            f"    <link href=\"{escape(base_url)}\" />\n"
            f"    <content type=\"text\">{escape(body)}</content>\n"
            f"  </entry>"
        )
    body_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <id>{escape(feed_id)}</id>\n"
        f"  <title>{escape(title)}</title>\n"
        f"  <updated>{escape(updated)}</updated>\n"
        f"  <link href=\"{escape(base_url)}\" rel=\"alternate\" />\n"
        f"  <link href=\"{escape(str(request.url))}\" rel=\"self\" />\n"
        + "\n".join(entries)
        + "\n</feed>\n"
    )
    return Response(content=body_xml, media_type="application/atom+xml")
