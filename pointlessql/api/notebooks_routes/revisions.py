"""Notebook revision routes (Phase 97).

Exposes the revision-history surface the editor's "History" panel
calls:

* ``POST   /api/notebooks/revisions`` — snapshot the current
  ``(cells + outputs)`` state.  Idempotent on the canonical hash;
  saving an unchanged notebook returns the existing revision.
* ``GET    /api/notebooks/revisions`` — list revisions for a path.
* ``GET    /api/notebooks/revisions/{uuid}`` — full payload (cells +
  outputs) for one revision; used by the Monaco diff side panel.
* ``GET    /api/notebooks/revisions/diff`` — cell-by-cell diff
  envelope between ``left`` and ``right`` revision UUIDs.

Signing via shoreguard-fresh is deferred until the shoreguard signing
API ships; the response shape already carries a ``signed`` boolean +
``signature_alg`` field so the front-end can render a verified badge
once signing lands.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import outputs as notebook_outputs_service
from pointlessql.services.notebook import revisions as notebook_revisions_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    """Resolve a ``?path=`` query into the stable notebook UUID."""
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/revisions")
async def api_list_revisions(
    request: Request,
    path: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    """List revisions for a notebook, newest first.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.
        limit: Newest-N cap (1–200, default 50).

    Returns:
        JSON ``{"path": ..., "notebook_id": ..., "revisions": [...]}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_revisions_service.list_revisions(
            session, notebook_id=notebook_id, limit=limit
        )
    return JSONResponse(
        {"path": path, "notebook_id": notebook_id, "revisions": rows}
    )


@router.post("/api/notebooks/revisions", status_code=201)
async def api_create_revision(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Snapshot the current notebook state.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{"path": <relative>, "message": <text|None>}``.
            The route loads cells + outputs server-side so the body
            does not have to carry them.

    Returns:
        JSON of the (new or pre-existing) revision row + ``created``
        flag indicating whether a new row was minted.

    Raises:
        ValidationError: On bad input shape.
    """
    require_user(request)
    path = body.get("path") if isinstance(body, dict) else None
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(path, str):
        raise ValidationError("body.path must be a string")
    if message is not None and not isinstance(message, str):
        raise ValidationError("body.message must be a string or null")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    notebook_id = get_or_create_notebook_uuid(request, relative)
    document = notebook_doc_service.load_document(absolute, relative)
    cells = [
        {
            "content_hash": cell.content_hash,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "result_var": cell.result_var,
            "tags": list(cell.tags),
        }
        for cell in document.cells
    ]
    outputs = notebook_outputs_service.load_outputs_for_path(
        request.app.state.session_factory, relative
    )
    factory = request.app.state.session_factory
    actor_email = None
    try:
        actor_email = request.state.user.get("email") if request.state.user else None
    except AttributeError:
        actor_email = None
    with factory() as session:
        existing_uuids = {
            r["revision_uuid"]
            for r in notebook_revisions_service.list_revisions(
                session, notebook_id=notebook_id, limit=200
            )
        }
        row = notebook_revisions_service.create_revision(
            session,
            notebook_id=notebook_id,
            cells=cells,
            outputs=outputs,
            created_by=actor_email,
            message=message,
        )
        created = row.revision_uuid not in existing_uuids
        envelope = notebook_revisions_service.row_to_envelope(row)
        session.commit()
    envelope["created"] = created
    logger.info(
        "notebook %s revision %s (%s)",
        notebook_id,
        envelope["revision_uuid"],
        "new" if created else "existing",
    )
    return JSONResponse(envelope, status_code=201)


@router.get("/api/notebooks/revisions/diff")
async def api_diff_revisions(
    request: Request,
    left: str = Query(..., min_length=36, max_length=36),
    right: str = Query(..., min_length=36, max_length=36),
) -> JSONResponse:
    """Return a cell-by-cell diff between two revisions.

    Args:
        request: Incoming request; any authenticated user.
        left: Older revision UUID.
        right: Newer revision UUID.

    Returns:
        JSON envelope ``{left_uuid, right_uuid, added, removed,
        changed, moved, unchanged}``; each list carries the cell
        dicts the Monaco diff editor wants.

    Raises:
        ValidationError: When either UUID is unknown.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_revisions_service.compute_diff(
            session, left_uuid=left, right_uuid=right
        )
    return JSONResponse(envelope)


@router.post("/api/notebooks/revisions/{revision_uuid}/signature")
async def api_set_revision_signature(
    request: Request,
    revision_uuid: str,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Persist an external signature on a revision (Phase 97 Wave-D).

    Admin-only receive surface for the deferred shoreguard sign-revision
    API or any other out-of-band signer (enterprise reviewer, CI job).
    Verification is not done on the server — the ``signature_alg``
    field tells consumers how to verify (e.g. ``ed25519:<key-id>``).
    The admin gate is the integrity barrier; a hostile admin could
    forge a signature, but a hostile admin can do anything else too.

    Args:
        request: Incoming request; admin required.
        revision_uuid: 36-char revision UUID.
        body: ``{"signature": <str>, "signature_alg": <str>}``.

    Returns:
        Updated envelope with ``signed=true``.

    Raises:
        AuthorizationError: When the caller is not an admin.
        ValidationError: On bad input shape or unknown revision.
    """
    require_user(request)
    user = getattr(request.state, "user", None) or {}
    if not bool(user.get("is_admin")):
        from pointlessql.exceptions import AuthorizationError

        raise AuthorizationError(
            principal=str(user.get("email") or "(anonymous)"),
            privilege="sign",
            securable_type="notebook_revision",
            full_name=revision_uuid,
        )
    signature = body.get("signature") if isinstance(body, dict) else None
    signature_alg = body.get("signature_alg") if isinstance(body, dict) else None
    if not isinstance(signature, str) or not isinstance(signature_alg, str):
        raise ValidationError(
            "body.signature and body.signature_alg must both be strings"
        )
    factory = request.app.state.session_factory
    with factory() as session:
        notebook_revisions_service.set_revision_signature(
            session,
            revision_uuid=revision_uuid,
            signature=signature,
            signature_alg=signature_alg,
        )
        envelope = notebook_revisions_service.get_revision(
            session, revision_uuid=revision_uuid
        )
        session.commit()
    return JSONResponse(envelope or {})


@router.get("/api/notebooks/revisions/{revision_uuid}")
async def api_get_revision(
    request: Request,
    revision_uuid: str,
) -> JSONResponse:
    """Return the full payload (cells + outputs) for one revision.

    Args:
        request: Incoming request; any authenticated user.
        revision_uuid: 36-char UUID minted at create time.

    Returns:
        JSON of the revision row including parsed ``cells`` and
        ``outputs`` arrays.

    Raises:
        ValidationError: When the UUID is unknown.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_revisions_service.get_revision(
            session, revision_uuid=revision_uuid
        )
    if envelope is None:
        raise ValidationError(f"revision {revision_uuid!r} not found")
    return JSONResponse(envelope)
