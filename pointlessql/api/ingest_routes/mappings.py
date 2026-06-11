"""table-mapping persistence.

``POST /api/ingest/sources/{id}/mappings`` replaces the source's
``table_mappings`` JSON column with a validated list of per-table
pull configurations.  Each mapping carries ``(source_table,
target_fqn, mode, high_water_col?)`` and is the unit the executor reads.

Validation rules:

* ``target_fqn`` must be ``catalog.schema.table`` (three dot-separated
  identifiers).  Invalid FQNs return HTTP 400.
* ``mode`` must be ``"full"`` or ``"incremental"``.
* When ``mode == "incremental"`` the mapping must carry a non-empty
  ``high_water_col``.
* ``pull_mode`` is optional; only ``"auto_loader"`` is persisted (it
  reroutes file-based pulls through the incremental file-discovery
  path) — ``"full_reload"`` / absence keeps the regular pull.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models import IngestSource
from pointlessql.models.ingest import INGEST_PULL_MODES
from pointlessql.services.ingest.autoloader import (
    AUTOLOADER_PULL_MODE,
    INGEST_FILE_PULL_MODES,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "mappings"])


def _validate_target_fqn(fqn: str) -> None:
    """Reject malformed catalog.schema.table strings.

    Args:
        fqn: Caller-supplied target FQN.

    Raises:
        ValidationError: When *fqn* doesn't have exactly 2 dots or
            any of its three segments is empty.
    """
    parts = fqn.split(".")
    if len(parts) != 3 or any(not p.strip() for p in parts):
        raise ValidationError(f"target_fqn must be 'catalog.schema.table', got {fqn!r}.")


def _validate_mapping(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce one mapping dict to its canonical shape.

    Args:
        raw: Caller-supplied mapping dict.

    Returns:
        Validated mapping with only the keys the executor reads.

    Raises:
        ValidationError: On any shape violation.
    """
    source_table = str(raw.get("source_table") or "").strip()
    target_fqn = str(raw.get("target_fqn") or "").strip()
    mode = str(raw.get("mode") or "full").strip()
    high_water_col_raw = raw.get("high_water_col")
    high_water_col = str(high_water_col_raw).strip() if high_water_col_raw else None
    pull_mode_raw = raw.get("pull_mode")
    pull_mode = str(pull_mode_raw).strip() if pull_mode_raw else ""

    if mode not in INGEST_PULL_MODES:
        raise ValidationError(f"mode must be one of {INGEST_PULL_MODES}, got {mode!r}.")
    if pull_mode and pull_mode not in INGEST_FILE_PULL_MODES:
        raise ValidationError(
            f"pull_mode must be one of {INGEST_FILE_PULL_MODES}, got {pull_mode!r}."
        )
    _validate_target_fqn(target_fqn)
    if mode == "incremental" and not high_water_col:
        raise ValidationError("incremental mode requires a non-empty high_water_col.")

    out: dict[str, Any] = {
        "source_table": source_table,
        "target_fqn": target_fqn,
        "mode": mode,
    }
    if high_water_col:
        out["high_water_col"] = high_water_col
    # Only the non-default pull mode is persisted — absence of the key
    # IS the default, keeping pre-existing mappings byte-identical.
    if pull_mode == AUTOLOADER_PULL_MODE:
        out["pull_mode"] = AUTOLOADER_PULL_MODE
    # Preserve previously-stored watermark + last-pull stats if the
    # caller round-tripped them; the executor will overwrite on the
    # next run.
    if "last_high_water_value" in raw:
        out["last_high_water_value"] = raw["last_high_water_value"]
    if "last_pull_stats" in raw:
        out["last_pull_stats"] = raw["last_pull_stats"]
    return out


@router.post("/api/ingest/sources/{source_id}/mappings")
async def api_replace_mappings(
    request: Request,
    source_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Replace the source's table_mappings with the supplied list.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.
        body: ``{"mappings": [...]}`` — each entry validated through
            :func:`_validate_mapping`.

    Returns:
        ``{"ok": True, "mappings": [...]}`` on success.

    Raises:
        ValidationError: On mapping validation failure.
        ResourceNotFoundError: When the source doesn't exist in the
            caller's workspace.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    raw_mappings = body.get("mappings")
    if not isinstance(raw_mappings, list):
        raise ValidationError("mappings must be a list.")

    validated: list[dict[str, Any]] = []
    for idx, m in enumerate(raw_mappings):  # type: ignore[reportUnknownVariableType]
        if not isinstance(m, dict):
            raise ValidationError(f"mappings[{idx}] must be an object.")
        try:
            validated.append(_validate_mapping(m))  # type: ignore[reportUnknownArgumentType]
        except ValidationError as exc:
            raise ValidationError(f"mappings[{idx}]: {exc}") from exc

    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        row.table_mappings = json.dumps(validated, default=str)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        stored = json.loads(row.table_mappings)

    return {"ok": True, "mappings": stored}
