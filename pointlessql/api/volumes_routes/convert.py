"""Convert a volume file to a managed Delta table."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    admin_uc,
    get_user,
)
from pointlessql.api.volumes_routes._shared import soyuz_base_url, volume_full_name_split
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["volumes"])

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
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, Any]:
    """Read a CSV / Parquet / JSON file in the volume into a new Delta table.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        body: JSON body with keys:

            - ``path`` (str, required): Volume-relative source path.
            - ``table_name`` (str, required): Target table name within
              the same schema as the volume.
        client: Per-request admin-gated UC facade injected by
            :func:`admin_uc`.

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
    settings: Settings = request.app.state.settings
    payload = body or {}
    rel_path = payload.get("path")
    table_name = payload.get("table_name")
    if not isinstance(rel_path, str) or not rel_path:
        raise ValidationError("Body must carry a non-empty 'path'.")
    if not isinstance(table_name, str) or not table_name:
        raise ValidationError("Body must carry a non-empty 'table_name'.")

    catalog_name, schema_name, volume_name = await volume_full_name_split(full_name)
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
