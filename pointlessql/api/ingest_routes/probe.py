"""Probe endpoint — dry-runs a configured reader.

``POST /api/ingest/probe`` accepts the in-form config + secrets,
hands them to :func:`pointlessql.services.ingest.probe.probe_source`,
and returns the resolved column list or a structured 400.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api.dependencies import require_user
from pointlessql.api.ingest_routes._serializers import (
    SECRETS_REDACTED_SENTINEL,
    merge_patch_secrets,
)
from pointlessql.exceptions import ValidationError
from pointlessql.models import IngestSource
from pointlessql.models.ingest import INGEST_SOURCE_KINDS
from pointlessql.services.ingest.probe import ProbeError, probe_source

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "probe"])


def _resolve_secrets_for_probe(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Stitch redacted ``"***"`` values back from the persisted source.

    The probe button on the *edit* form posts the same body shape the
    GET response returned — including ``"***"`` placeholders.  If the
    body carries a ``source_id`` we look up the existing row and
    merge the real secrets in where the body said ``"***"``.

    Args:
        request: Incoming FastAPI request.
        body: Probe request body.

    Returns:
        Secrets dict ready for ``probe_source``.
    """
    raw: object = body.get("secrets") or {}
    if not isinstance(raw, dict):
        raw = {}
    body_secrets: dict[str, Any] = {str(k): v for k, v in cast(dict[Any, Any], raw).items()}
    source_id = body.get("source_id")
    if source_id is None:
        # Stripping any leftover ``***`` sentinel — on create-probe we
        # have nothing to merge against, so a redacted value means
        # "no value".
        return {k: v for k, v in body_secrets.items() if v != SECRETS_REDACTED_SENTINEL}
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, int(source_id))
        if row is None:
            return {k: v for k, v in body_secrets.items() if v != SECRETS_REDACTED_SENTINEL}
        return merge_patch_secrets(row.secrets or "{}", body_secrets)


@router.post("/api/ingest/probe")
async def api_probe(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Dry-run a reader and return resolved columns.

    Args:
        request: Incoming FastAPI request.
        body: ``{kind, config, secrets, source_table?, source_id?}``.

    Returns:
        On success: ``{"ok": True, "columns": [...], "extension_ms",
        "query_ms"}``.

    Raises:
        ValidationError: On invalid ``kind`` / structured probe
            failure.
    """
    require_user(request)
    kind = str(body.get("kind") or "").strip()
    if kind not in INGEST_SOURCE_KINDS:
        raise ValidationError(
            f"kind must be one of {INGEST_SOURCE_KINDS}, got {kind!r}.",
        )
    config_raw: object = body.get("config") or {}
    if not isinstance(config_raw, dict):
        raise ValidationError("config must be an object.")
    config: dict[str, Any] = {str(k): v for k, v in cast(dict[Any, Any], config_raw).items()}
    source_table = body.get("source_table")
    if source_table is not None and not isinstance(source_table, str):
        raise ValidationError("source_table must be a string or absent.")

    secrets = _resolve_secrets_for_probe(request, body)

    try:
        result = probe_source(
            kind,
            config,
            secrets,
            source_table=source_table,  # type: ignore[arg-type]
        )
    except ProbeError as exc:
        return _probe_error_response(exc)

    payload: dict[str, Any] = {"ok": True}
    payload.update(result.to_dict())
    return payload


def _probe_error_response(exc: ProbeError) -> dict[str, Any]:
    """Turn a :class:`ProbeError` into a 200 envelope with ``ok=False``.

    A 200 with ``ok=False`` is friendlier for the form UX than a 400
    because the front end's fetch helper raises on 4xx by default —
    surfacing the reason + hint inline is cheaper than threading
    custom error handling through every Probe button.

    Args:
        exc: The probe error to surface.

    Returns:
        Envelope dict the front-end can read.
    """
    return {
        "ok": False,
        "reason": exc.reason,
        "hint": exc.hint,
    }
