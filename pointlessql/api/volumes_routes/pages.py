"""Server-rendered volume browser HTML pages."""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    get_templates,
    get_uc_client,
    get_user,
)
from pointlessql.api.volumes_routes._shared import soyuz_base_url, volume_full_name_split

logger = logging.getLogger(__name__)

router = APIRouter(tags=["volumes"])


@router.get("/volumes", response_class=HTMLResponse)
async def volumes_page(request: Request) -> HTMLResponse:
    """Render the volumes list page.

    Iterates every catalog the caller can see and aggregates the
    per-schema volume lists from soyuz.  Non-admin callers see only
    the catalogs they hold ``USE_CATALOG`` on — enforcement already
    lives on soyuz's list endpoints.

    Args:
        request: Incoming request.

    Returns:
        HTML response.
    """
    uc_client = get_uc_client(request)
    volumes: list[dict[str, Any]] = []
    try:
        catalogs = await uc_client.list_catalogs()
    except Exception:  # noqa: BLE001 — tolerate a broken soyuz
        logger.exception("volumes page: list_catalogs failed")
        catalogs = []
    user = get_user(request)
    from pointlessql.services import volumes as vol_service

    async with httpx.AsyncClient(
        timeout=vol_service.proxy_timeout(request.app.state.settings)
    ) as http_client:
        for cat in catalogs or []:
            try:
                schemas = await uc_client.list_schemas(cat["name"])
            except Exception:  # noqa: BLE001
                logger.debug(
                    "volumes page: list_schemas %s failed",
                    cat.get("name"),
                    exc_info=True,
                )
                continue
            for sch in schemas or []:
                url = (
                    f"{soyuz_base_url(request)}"
                    f"/api/2.1/unity-catalog/volumes"
                    f"?catalog_name={cat['name']}&schema_name={sch['name']}"
                )
                try:
                    resp = await http_client.get(
                        url,
                        headers={"X-Principal": user.get("email") or ""},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    raw_volumes: list[dict[str, Any]] = []
                    if isinstance(data, dict):
                        data_dict = cast(dict[str, Any], data)
                        raw_volumes = cast(
                            list[dict[str, Any]],
                            data_dict.get("volumes") or [],
                        )
                    for v in raw_volumes:
                        volumes.append(
                            {
                                "full_name": v.get("full_name"),
                                "name": v.get("name"),
                                "catalog_name": v.get("catalog_name"),
                                "schema_name": v.get("schema_name"),
                                "storage_location": v.get("storage_location"),
                                "volume_type": v.get("volume_type"),
                            },
                        )
                except Exception:  # noqa: BLE001
                    logger.debug("volumes page: fetch failed", exc_info=True)
    return get_templates(request).TemplateResponse(
        request,
        "pages/volumes.html",
        {
            "volumes": volumes,
            "active_page": "volumes",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@router.get("/volumes/{full_name:path}", response_class=HTMLResponse)
async def volume_detail_page(request: Request, full_name: str) -> HTMLResponse:
    """Render the per-volume detail page with upload + browse surface.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.

    Returns:
        HTML response.

    Raises:
        CatalogNotFoundError: When soyuz returns 404 for the volume.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import volumes as vol_service

    await volume_full_name_split(full_name)
    user = get_user(request)
    async with httpx.AsyncClient(
        timeout=vol_service.proxy_timeout(request.app.state.settings)
    ) as client:
        # Look up metadata via a raw soyuz GET so we can surface
        # storage_location in the UI.
        meta = await client.get(
            f"{soyuz_base_url(request)}/api/2.1/unity-catalog/volumes/{full_name}",
            headers={"X-Principal": user.get("email") or ""},
        )
        if meta.status_code == 404:
            raise CatalogNotFoundError(f"Volume {full_name!r} not found.")
        meta.raise_for_status()
        volume = meta.json()
        # A managed volume with no storage_location yet (freshly created,
        # never materialised) has nothing to browse — soyuz 400s the /files
        # endpoint for it. Skip the doomed call and let the template render
        # the empty-files state it already provides, rather than 500-ing.
        if volume.get("storage_location"):
            files = await vol_service.browse_files(
                client,
                soyuz_base_url(request),
                full_name,
                principal=user.get("email"),
            )
        else:
            files = []
    return get_templates(request).TemplateResponse(
        request,
        "pages/volume_detail.html",
        {
            "volume": volume,
            "files": files,
            "active_page": "volumes",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
