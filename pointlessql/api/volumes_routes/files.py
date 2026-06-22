"""Volume file browse / upload / delete JSON endpoints."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    get_user,
)
from pointlessql.api.volumes_routes._shared import soyuz_base_url, volume_full_name_split

logger = logging.getLogger(__name__)

router = APIRouter(tags=["volumes"])


@router.get("/api/volumes/{full_name:path}/files")
async def api_browse_volume(
    request: Request,
    full_name: str,
) -> dict[str, list[dict[str, Any]]]:
    """List every file stored on *full_name*.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.

    Returns:
        Dict with a ``files`` list in soyuz's serialisation.
    """
    from pointlessql.services import volumes as vol_service

    await volume_full_name_split(full_name)
    user = get_user(request)
    async with httpx.AsyncClient() as client:
        files = await vol_service.browse_files(
            client,
            soyuz_base_url(request),
            full_name,
            principal=user.get("email"),
        )
    return {"files": files}


@router.post("/api/volumes/{full_name:path}/files")
async def api_upload_volume_file(
    request: Request,
    full_name: str,
    path: str = Form(...),
    upload: UploadFile = File(...),
) -> dict[str, Any]:
    """Proxy a multipart upload into soyuz's volume storage backend.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        path: Volume-relative destination path.
        upload: The ``multipart/form-data`` body.

    Returns:
        Dict with the resulting file entry.

    Raises:
        HTTPException: 413 when the uploaded body exceeds
            ``server.max_request_bytes``.
    """
    from pointlessql.services import volumes as vol_service

    await volume_full_name_split(full_name)
    user = get_user(request)
    data = await upload.read()
    # Backstop the Content-Length middleware for chunked uploads that
    # carry no length header: reject once the body is in hand.
    max_bytes = int(request.app.state.settings.server.max_request_bytes)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail="Uploaded file exceeds the maximum allowed size."
        )
    async with httpx.AsyncClient() as client:
        body = await vol_service.upload_file(
            client,
            soyuz_base_url(request),
            full_name,
            path=path,
            upload_name=upload.filename or path,
            upload_bytes=data,
            principal=user.get("email"),
            content_type=upload.content_type or "application/octet-stream",
        )
    await audit(
        request,
        "volume.file_uploaded",
        f"volume:{full_name}",
        {"path": path, "bytes": len(data)},
    )
    return body


@router.delete("/api/volumes/{full_name}/files/{path:path}", status_code=204)
async def api_delete_volume_file(
    request: Request,
    full_name: str,
    path: str,
) -> Response:
    """Remove a single file from a volume.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        path: Volume-relative source path.

    Returns:
        Empty 204.
    """
    from pointlessql.services import volumes as vol_service

    await volume_full_name_split(full_name)
    user = get_user(request)
    async with httpx.AsyncClient() as client:
        await vol_service.delete_file(
            client,
            soyuz_base_url(request),
            full_name,
            path,
            principal=user.get("email"),
        )
    await audit(
        request,
        "volume.file_deleted",
        f"volume:{full_name}",
        {"path": path},
    )
    return Response(status_code=204)
