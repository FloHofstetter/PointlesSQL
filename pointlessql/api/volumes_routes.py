"""UC volumes routes — files CRUD + convert-to-Delta + HTML pages.

Owns the four JSON endpoints (browse / upload / delete a single
file + convert-to-Delta) and the two HTML pages (volumes list +
per-volume detail with the upload + browse surface).

The convert-to-Delta endpoint also owns the Delta → UC type mapping
(``DELTA_PRIMITIVE_TO_UC`` + ``delta_field_to_uc``) — the only
non-route-shaped logic in the file.  ``api/main.py`` re-exports the
mapping under the legacy ``_DELTA_PRIMITIVE_TO_UC`` /
``_delta_field_to_uc`` names so
``tests/test_volume_convert_type_mapping.py`` keeps importing them
from ``pointlessql.api.main``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_uc_client, get_user, require_admin
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["volumes"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def soyuz_base_url(request: Request) -> str:
    """Return the configured soyuz-catalog base URL.

    Args:
        request: Incoming request.

    Returns:
        The base URL string (without trailing slash).
    """
    settings: Settings = request.app.state.settings
    return settings.soyuz.catalog_url.rstrip("/")


async def volume_full_name_split(full_name: str) -> tuple[str, str, str]:
    """Split *full_name* into its UC three parts or raise.

    Args:
        full_name: Dotted identifier.

    Returns:
        Tuple ``(catalog, schema, volume)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.volume, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]


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
    """
    from pointlessql.services import volumes as vol_service

    await volume_full_name_split(full_name)
    user = get_user(request)
    data = await upload.read()
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


def convert_volume_file_sync(
    settings: Settings,
    *,
    source_file: Path,
    source_format: str,
    target_location: str,
) -> None:
    """Read *source_file* via DuckDB and write it as a Delta table.

    Runs under ``asyncio.to_thread`` so the request handler keeps
    serving other requests during the convert pass.

    Args:
        settings: Application settings (reserved; forward-compatible
            hook for engine selection).
        source_file: Absolute path of the CSV / Parquet / JSON source.
        source_format: ``"csv"`` / ``"parquet"`` / ``"json"``.
        target_location: ``file://`` URI for the managed Delta output.

    Raises:
        ValidationError: On an unsupported ``source_format``.
    """
    import duckdb

    del settings
    reader = {
        "csv": "read_csv_auto",
        "parquet": "read_parquet",
        "json": "read_json_auto",
    }.get(source_format)
    if reader is None:
        raise ValidationError(
            f"Unsupported convert source format {source_format!r}; "
            "expected one of csv / parquet / json.",
        )
    conn = duckdb.connect()
    try:
        arrow_table = conn.execute(
            f"SELECT * FROM {reader}('{source_file}')",
        ).to_arrow_table()
    finally:
        conn.close()
    # deltalake writes the target dir in place; target_location may
    # be a file:// URI which deltalake accepts verbatim.
    import deltalake

    deltalake.write_deltalake(target_location, arrow_table, mode="overwrite")


# Delta ``PrimitiveType.type`` string → UC ``(type_name, type_text)``.
# Mirrors the DuckDB / UC type codes used by
# :mod:`pointlessql.pql.engine` for sync-path table rows, but keyed
# off the Delta schema surface rather than the DuckDB one so the
# convert-to-Delta flow can register columns with correct numeric
# types instead of falling back to ``string``.
DELTA_PRIMITIVE_TO_UC: dict[str, tuple[str, str]] = {
    "boolean": ("BOOLEAN", "boolean"),
    "byte": ("BYTE", "byte"),
    "short": ("SHORT", "short"),
    "integer": ("INT", "int"),
    "long": ("LONG", "long"),
    "float": ("FLOAT", "float"),
    "double": ("DOUBLE", "double"),
    "date": ("DATE", "date"),
    "timestamp": ("TIMESTAMP", "timestamp"),
    "timestampntz": ("TIMESTAMP_NTZ", "timestamp_ntz"),
    "string": ("STRING", "string"),
    "binary": ("BINARY", "binary"),
}


def delta_field_to_uc(field: Any) -> tuple[str, str]:
    """Map a ``deltalake`` schema field to UC ``(type_name, type_text)``.

    ``deltalake`` exposes a field's type as a ``PrimitiveType`` (or a
    compound type) whose ``type`` attribute is a lowercase Delta type
    code — ``"long"`` / ``"double"`` / ``"string"`` and so on.  Compound
    types (structs, arrays, maps) stringify to a JSON-like repr and
    fall back to ``("STRING", "string")`` for now — they can be mapped
    properly when an agent workload actually depends on the
    distinction.

    Args:
        field: A ``deltalake.Field``-shaped object with ``.type``.

    Returns:
        Tuple of UC ``type_name`` and ``type_text``.
    """
    prim = getattr(field.type, "type", None)
    if isinstance(prim, str):
        return DELTA_PRIMITIVE_TO_UC.get(prim.lower(), ("STRING", "string"))
    return ("STRING", "string")


@router.post("/api/volumes/{full_name:path}/convert-to-delta")
async def api_convert_volume_file_to_delta(
    request: Request,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Read a CSV / Parquet / JSON file in the volume into a new Delta table.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        body: JSON body with keys:

            - ``path`` (str, required): Volume-relative source path.
            - ``table_name`` (str, required): Target table name within
              the same schema as the volume.

    Returns:
        Dict with the created table row from UC.

    Raises:
        ValidationError: If the body is missing required keys or
            points at an unsupported format.
        CatalogNotFoundError: When soyuz cannot find the volume or
            its storage is not ``file://``.
    """  # noqa: DOC502,DOC503 — raised below
    import tempfile

    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import volumes as vol_service

    user = get_user(request)
    require_admin(request)
    settings: Settings = request.app.state.settings
    payload = body or {}
    rel_path = payload.get("path")
    table_name = payload.get("table_name")
    if not isinstance(rel_path, str) or not rel_path:
        raise ValidationError("Body must carry a non-empty 'path'.")
    if not isinstance(table_name, str) or not table_name:
        raise ValidationError("Body must carry a non-empty 'table_name'.")

    catalog_name, schema_name, volume_name = await volume_full_name_split(full_name)
    client = get_uc_client(request)
    # Raw soyuz GET — the UnityCatalogClient wrapper does not expose
    # volumes yet.  Keep the call narrow; result is a dict, not a
    # typed model.
    async with httpx.AsyncClient() as http:
        v_response = await http.get(
            f"{soyuz_base_url(request)}/api/2.1/unity-catalog/volumes/{full_name}",
            headers={"X-Principal": user.get("email") or ""},
        )
        if v_response.status_code == 404:
            raise CatalogNotFoundError(f"Volume {full_name!r} not found.")
        v_response.raise_for_status()
        volume_info = v_response.json()

    storage_location = volume_info.get("storage_location") or ""
    if not storage_location.startswith("file://"):
        raise ValidationError(
            f"Convert-to-Delta currently supports only file:// volumes; got {storage_location!r}.",
        )

    # Download the source file out of soyuz into a temp dir, convert
    # via DuckDB, write Delta under the same volume path, then
    # register a managed table in UC.
    ext = rel_path.rsplit(".", 1)[-1].lower()
    source_format = {"csv": "csv", "parquet": "parquet", "json": "json"}.get(ext)
    if source_format is None:
        raise ValidationError(
            "Unsupported source format.  Expected .csv / .parquet / .json "
            f"extension on {rel_path!r}.",
        )

    async with httpx.AsyncClient() as http_client:
        # Stream into a temp file.
        target_path = Path(tempfile.mkstemp(suffix=f".{ext}")[1])
        try:
            async for chunk in vol_service.download_file(
                http_client,
                soyuz_base_url(request),
                full_name,
                rel_path,
                principal=user.get("email"),
            ):
                with target_path.open("ab") as fh:
                    fh.write(chunk)
            # Convert path: resolve a Delta target under the volume's
            # file:// root so the bytes stay inside the volume the
            # user already has rights on.
            volume_root = storage_location[len("file://") :]
            delta_dir = Path(volume_root) / f"_delta_{table_name}"
            delta_dir.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                convert_volume_file_sync,
                settings,
                source_file=target_path,
                source_format=source_format,
                target_location=str(delta_dir),
            )
        finally:
            target_path.unlink(missing_ok=True)

    # Derive columns by peeking at the fresh Delta dir.
    import deltalake

    dt = deltalake.DeltaTable(str(delta_dir))
    schema_fields = dt.schema().fields
    columns: list[dict[str, Any]] = []
    for position, field in enumerate(schema_fields):
        type_name, type_text = delta_field_to_uc(field)
        columns.append(
            {
                "name": field.name,
                "type_name": type_name,
                "type_text": type_text,
                "type_json": "{}",
                "type_precision": 0,
                "type_scale": 0,
                "position": position,
                "nullable": field.nullable,
            },
        )

    register_payload = {
        "name": table_name,
        "catalog_name": catalog_name,
        "schema_name": schema_name,
        "table_type": "EXTERNAL",
        "data_source_format": "DELTA",
        "columns": columns,
        "storage_location": f"file://{delta_dir}",
    }
    created = await client.create_table(register_payload)
    await audit(
        request,
        "volume.converted_to_delta",
        f"volume:{full_name}",
        {"path": rel_path, "table": table_name, "columns": len(columns)},
    )
    _ = (catalog_name, schema_name, volume_name)  # silence unused
    return created


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
    async with httpx.AsyncClient() as http_client:
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
    return _templates(request).TemplateResponse(
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
    async with httpx.AsyncClient() as client:
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
        files = await vol_service.browse_files(
            client,
            soyuz_base_url(request),
            full_name,
            principal=user.get("email"),
        )
    return _templates(request).TemplateResponse(
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
