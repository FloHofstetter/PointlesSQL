"""Notebook share routes.

Two surfaces:

* **Admin CRUD** under ``/api/notebooks/shares`` — publish / list /
  update / unpublish.  Cookie-gated, workspace-scoped.
* **Public viewer** under ``/share/notebook/{share_uuid}`` —
  unauthenticated read-only render.  Serves either the regular HTML
  (Phase-98.D export pipeline) or the dashboard variant.

Snapshot mode pins the share to a Phase-97 :class:`NotebookRevision`
so subsequent edits do not leak; live mode reads the current ``.py``
plus the latest persisted outputs.  Both modes scrub nothing
automatically — the publish step is admin-gated and the publisher
is expected to vet the content before minting the link.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import get_optional_user, require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import export as notebook_export_service
from pointlessql.services.notebook import (
    outputs as notebook_outputs_service,
)
from pointlessql.services.notebook import (
    revisions as notebook_revisions_service,
)
from pointlessql.services.notebook import shares as notebook_shares_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/shares")
async def api_list_shares(request: Request, path: str = Query(..., min_length=1)) -> JSONResponse:
    """List shares (active + revoked) for one notebook."""
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_shares_service.list_shares_for_notebook(session, notebook_id=notebook_id)
    return JSONResponse({"path": path, "notebook_id": notebook_id, "shares": rows})


@router.post("/api/notebooks/shares", status_code=201)
async def api_create_share(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Publish a notebook.

    Body keys:
        path: Relative notebook path.
        share_mode: ``"snapshot"`` *(default)* or ``"live"``.
        dashboard_mode: Optional bool; default ``false``.
        message: Optional revision message for snapshot mode.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    share_mode = body.get("share_mode", "snapshot")
    dashboard_mode = bool(body.get("dashboard_mode", False))
    message = body.get("message")
    if not isinstance(path, str):
        raise ValidationError("body.path must be a string")
    if share_mode not in notebook_shares_service.VALID_SHARE_MODES:
        raise ValidationError(
            f"share_mode must be one of {notebook_shares_service.VALID_SHARE_MODES}"
        )

    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    notebook_id = get_or_create_notebook_uuid(request, relative)
    actor = get_optional_user(request)
    actor_id: int | None = actor.get("id") if actor else None

    revision_uuid: str | None = None
    factory = request.app.state.session_factory
    if share_mode == "snapshot":
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
        outputs = notebook_outputs_service.load_outputs_for_path(factory, relative)
        with factory() as session:
            rev = notebook_revisions_service.create_revision(
                session,
                notebook_id=notebook_id,
                cells=cells,
                outputs=outputs,
                created_by=None,
                message=message if isinstance(message, str) else None,
            )
            revision_uuid = rev.revision_uuid
            session.commit()

    with factory() as session:
        share = notebook_shares_service.create_share(
            session,
            notebook_id=notebook_id,
            share_mode=share_mode,
            dashboard_mode=dashboard_mode,
            revision_uuid=revision_uuid,
            created_by_user_id=actor_id,
        )
        envelope = {
            "share_uuid": share.share_uuid,
            "share_mode": share.share_mode,
            "dashboard_mode": share.dashboard_mode,
            "revision_uuid": share.revision_uuid,
            "share_url": f"/share/notebook/{share.share_uuid}",
        }
        session.commit()
    logger.info(
        "notebook %s shared as %s (%s, dashboard=%s)",
        notebook_id,
        envelope["share_uuid"],
        share_mode,
        dashboard_mode,
    )
    return JSONResponse(envelope, status_code=201)


@router.patch("/api/notebooks/shares/{share_uuid}")
async def api_update_share(
    request: Request,
    share_uuid: str,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update an existing share (toggle mode / dashboard, re-pin revision)."""
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    share_mode_raw = body.get("share_mode")
    dashboard_mode_raw = body.get("dashboard_mode")
    revision_uuid_raw = body.get("revision_uuid")
    if share_mode_raw is not None and not isinstance(share_mode_raw, str):
        raise ValidationError("body.share_mode must be a string or null")
    if dashboard_mode_raw is not None and not isinstance(dashboard_mode_raw, bool):
        raise ValidationError("body.dashboard_mode must be bool or null")
    if revision_uuid_raw is not None and not isinstance(revision_uuid_raw, str):
        raise ValidationError("body.revision_uuid must be a string or null")
    factory = request.app.state.session_factory
    with factory() as session:
        share = notebook_shares_service.update_share(
            session,
            share_uuid=share_uuid,
            share_mode=share_mode_raw,  # type: ignore[arg-type]
            dashboard_mode=dashboard_mode_raw,
            revision_uuid=revision_uuid_raw,
        )
        envelope = {
            "share_uuid": share.share_uuid,
            "share_mode": share.share_mode,
            "dashboard_mode": share.dashboard_mode,
            "revision_uuid": share.revision_uuid,
        }
        session.commit()
    return JSONResponse(envelope)


@router.delete("/api/notebooks/shares/{share_uuid}")
async def api_revoke_share(request: Request, share_uuid: str) -> JSONResponse:
    """Soft-revoke a share; idempotent."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        removed = notebook_shares_service.revoke_share(session, share_uuid=share_uuid)
        session.commit()
    return JSONResponse({"revoked": removed})


async def _render_share(request: Request, share_uuid: str, *, compact: bool) -> Response:
    """Render the shared body used by :func:`public_share_view` + :func:`public_share_embed`.

    Resolves the row, picks the revision or live source, scrubs outputs,
    then renders the cells fragment into the stripped-down public Jinja
    layout (``base_public.html`` + ``notebook_share_public.html``).  The
    layout brings its own brand topbar so the share view feels like part
    of PointlesSQL instead of a context-free standalone export.  The
    ``compact`` flag suppresses the topbar for iframe embeds where the
    surrounding page already provides chrome.

    Returns ``410 Gone`` for revoked / expired shares + missing assets so
    external link-checkers can drop dead links automatically.
    """
    factory = request.app.state.session_factory
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    with factory() as session:
        share = notebook_shares_service.get_active_share(session, share_uuid=share_uuid)
        if share is None:
            return Response(
                content="share is revoked or expired",
                status_code=410,
                media_type="text/plain",
            )
        notebook = session.get(Notebook, share.notebook_id)
        title = notebook.file_path.removesuffix(".py") if notebook else "notebook"
        if share.share_mode == "snapshot" and share.revision_uuid:
            rev = notebook_revisions_service.get_revision(
                session, revision_uuid=share.revision_uuid
            )
            if rev is None:
                return Response(
                    content="share's pinned revision is missing",
                    status_code=410,
                    media_type="text/plain",
                )
            cells = rev["cells"]
            outputs = rev["outputs"]
            dashboard = share.dashboard_mode
        else:
            if notebook is None:
                return Response(
                    content="share's notebook is missing",
                    status_code=410,
                    media_type="text/plain",
                )
            absolute = notebooks_dir / notebook.file_path
            if not absolute.exists():
                return Response(
                    content="share's notebook is missing on disk",
                    status_code=410,
                    media_type="text/plain",
                )
            document = notebook_doc_service.load_document(absolute, notebook.file_path)
            cells = [
                {
                    "content_hash": cell.content_hash,
                    "cell_type": cell.cell_type,
                    "source": cell.source,
                }
                for cell in document.cells
            ]
            outputs = notebook_outputs_service.load_outputs_for_path(factory, notebook.file_path)
            dashboard = share.dashboard_mode

    scrubbed_outputs = notebook_shares_service.scrub_outputs(outputs)
    if dashboard:
        filtered_cells: list[dict[str, Any]] = []
        relevant_hashes = {c.get("content_hash") for c in cells}
        for cell in cells:
            if (cell.get("cell_type") or "code") == "markdown":
                filtered_cells.append(cell)
            else:
                filtered_cells.append(
                    {
                        "content_hash": cell.get("content_hash") or "",
                        "cell_type": "markdown",
                        "source": "",
                    }
                )
        scrubbed_outputs = [o for o in scrubbed_outputs if o.get("content_hash") in relevant_hashes]
        cells_for_render = filtered_cells
    else:
        cells_for_render = cells

    body_html = notebook_export_service.render_notebook_body_html(
        cells=cells_for_render, outputs=scrubbed_outputs
    )
    import datetime as _dt

    exported_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/notebook_share_public.html",
        {
            "title": title,
            "exported_at": exported_at,
            "cell_count": len(cells_for_render),
            "body_html": body_html,
            "dashboard_mode": bool(dashboard),
            "compact": compact,
        },
    )


@router.get("/share/notebook/{share_uuid}")
async def public_share_view(request: Request, share_uuid: str) -> Response:
    """Render the share publicly (no auth).

    See :func:`_render_share` for the shared resolution + render logic.
    """
    return await _render_share(request, share_uuid, compact=False)


@router.get("/embed/notebook_share/{share_uuid}")
async def public_share_embed(request: Request, share_uuid: str) -> Response:
    """Iframe-friendly variant of :func:`public_share_view`.

    Same content + same secret-scrub; ``compact=True`` hides the brand
    topbar so the iframe parent owns the chrome.
    """
    return await _render_share(request, share_uuid, compact=True)
