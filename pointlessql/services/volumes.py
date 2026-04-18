"""HTTP helpers for the soyuz-catalog Volumes surface (Sprint 57).

The generated ``soyuz-catalog-client`` ships metadata CRUD for
volumes but the file IO endpoints — upload / browse / download /
delete — landed in a later soyuz release and have not been
regenerated into the pinned wheel yet.  Rather than block Phase
12.5 on a client-regen round-trip, this module calls the endpoints
directly via ``httpx`` using the same ``settings.soyuz.catalog_url``
the generated client is configured with, and forwards
``X-Principal`` so soyuz applies the right identity.

Every helper is async and requires a caller-supplied
:class:`httpx.AsyncClient` so tests can inject a
:class:`httpx.MockTransport` instead of touching the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx


def build_headers(principal: str | None) -> dict[str, str]:
    """Return headers for a soyuz volume file IO request.

    Args:
        principal: Optional ``X-Principal`` value.

    Returns:
        Dict of HTTP headers ready for :meth:`httpx.AsyncClient.request`.
    """
    headers: dict[str, str] = {}
    if principal:
        headers["X-Principal"] = principal
    return headers


def volume_url(base_url: str, full_name: str, *, path: str = "") -> str:
    """Return the soyuz URL for the volume file endpoint.

    Args:
        base_url: The soyuz-catalog base URL (``settings.soyuz.catalog_url``).
        full_name: Dotted UC identifier.
        path: When non-empty, append ``/{path}`` as the per-file suffix.

    Returns:
        A ready-to-request URL.
    """
    root = base_url.rstrip("/")
    suffix = f"/{path.lstrip('/')}" if path else ""
    return f"{root}/api/2.1/unity-catalog/volumes/{full_name}/files{suffix}"


async def upload_file(
    client: httpx.AsyncClient,
    base_url: str,
    full_name: str,
    *,
    path: str,
    upload_name: str,
    upload_bytes: bytes,
    principal: str | None,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Stream *upload_bytes* into soyuz as a multipart upload.

    Args:
        client: The caller-owned async client.
        base_url: Soyuz-catalog base URL.
        full_name: Dotted UC volume identifier.
        path: Volume-relative destination path.
        upload_name: Filename passed through the multipart form.
        upload_bytes: Raw file bytes.
        principal: Optional ``X-Principal`` value.
        content_type: MIME type for the multipart part.

    Returns:
        The soyuz JSON response body.
    """  # noqa: DOC502 — httpx raises non-locally via raise_for_status
    files = {"upload": (upload_name, upload_bytes, content_type)}
    response = await client.post(
        volume_url(base_url, full_name),
        params={"path": path},
        files=files,
        headers=build_headers(principal),
    )
    response.raise_for_status()
    return response.json()


async def browse_files(
    client: httpx.AsyncClient,
    base_url: str,
    full_name: str,
    *,
    principal: str | None,
) -> list[dict[str, Any]]:
    """Return every file listed under *full_name*.

    Args:
        client: Async client.
        base_url: Soyuz-catalog base URL.
        full_name: Dotted UC volume identifier.
        principal: Optional ``X-Principal`` value.

    Returns:
        List of file-entry dicts in soyuz's serialisation.
    """  # noqa: DOC502 — httpx raise_for_status propagates non-locally
    response = await client.get(
        volume_url(base_url, full_name),
        headers=build_headers(principal),
    )
    response.raise_for_status()
    body = response.json()
    return list(body.get("files") or [])


async def download_file(
    client: httpx.AsyncClient,
    base_url: str,
    full_name: str,
    path: str,
    *,
    principal: str | None,
) -> AsyncIterator[bytes]:
    """Stream the bytes for *path* out of soyuz.

    Args:
        client: Async client.
        base_url: Soyuz-catalog base URL.
        full_name: Dotted UC volume identifier.
        path: Volume-relative source path.
        principal: Optional ``X-Principal`` value.

    Yields:
        Successive byte chunks straight from soyuz's
        ``FileResponse``.
    """  # noqa: DOC502 — httpx raise_for_status propagates non-locally
    async with client.stream(
        "GET",
        volume_url(base_url, full_name, path=path),
        headers=build_headers(principal),
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk


async def delete_file(
    client: httpx.AsyncClient,
    base_url: str,
    full_name: str,
    path: str,
    *,
    principal: str | None,
) -> bool:
    """Remove *path* from the volume.

    Args:
        client: Async client.
        base_url: Soyuz-catalog base URL.
        full_name: Dotted UC volume identifier.
        path: Volume-relative source path.
        principal: Optional ``X-Principal`` value.

    Returns:
        ``True`` iff soyuz reports the file was deleted.
    """  # noqa: DOC502 — httpx raise_for_status propagates non-locally
    response = await client.delete(
        volume_url(base_url, full_name, path=path),
        headers=build_headers(principal),
    )
    response.raise_for_status()
    return bool(response.json().get("deleted"))
