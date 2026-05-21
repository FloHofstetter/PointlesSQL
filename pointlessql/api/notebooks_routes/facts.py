"""Pinned-fact REST routes (Phase 97 Rest).

Backs the editor's Diff-Drawer + Cell-Header "📌 Pin as fact" actions
and the workspace's ``/library/facts`` browse page.

Endpoints:

* ``POST   /api/notebooks/facts`` — promote a revision (or one cell
  output) into a fact.  Idempotent on
  ``(workspace_id, revision, cell_content_hash)`` while active.
* ``GET    /api/notebooks/facts`` — list facts in the active workspace,
  newest-pinned first; supports ``?notebook_path=...`` filter.
* ``GET    /api/notebooks/facts/{fact_uuid}`` — detail with the result
  snapshot expanded.
* ``DELETE /api/notebooks/facts/{fact_uuid}`` — soft-delete (stamp
  ``unpinned_at``).
* ``GET    /api/notebooks/facts/bulk`` — bulk active-fact lookup keyed
  by cell ``content_hash`` for the editor's per-cell pin chip.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.api.notebooks_routes._shared import (
    get_or_create_notebook_uuid,
    templates,
)
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import facts as notebook_facts_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_id(request: Request, path: str) -> str:
    """Resolve a ``?notebook_path=`` query string into the notebook UUID."""
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.post("/api/notebooks/facts", status_code=201)
async def api_pin_fact(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Promote a revision (or cell output) into a pinned fact.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{"revision_uuid": str, "title": str,
            "description_md": str|null, "cell_content_hash": str|null,
            "result_snapshot_json": str|null}``.

    Returns:
        JSON envelope of the new (or pre-existing active) fact row,
        plus the source revision UUID and notebook id for the
        front-end to redirect.

    Raises:
        ValidationError: On bad shape, unknown revision, or cross-
            workspace pin attempt.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    user = getattr(request.state, "user", None) or {}
    user_id_raw = user.get("id") if isinstance(user, dict) else None
    pinned_by_user_id = int(user_id_raw) if user_id_raw is not None else None

    revision_uuid = body.get("revision_uuid") if isinstance(body, dict) else None
    title = body.get("title") if isinstance(body, dict) else None
    description_md = body.get("description_md") if isinstance(body, dict) else None
    cell_content_hash = (
        body.get("cell_content_hash") if isinstance(body, dict) else None
    )
    result_snapshot_json = (
        body.get("result_snapshot_json") if isinstance(body, dict) else None
    )
    if not isinstance(revision_uuid, str):
        raise ValidationError("body.revision_uuid must be a string")
    if not isinstance(title, str):
        raise ValidationError("body.title must be a string")
    if description_md is not None and not isinstance(description_md, str):
        raise ValidationError("body.description_md must be a string or null")
    if cell_content_hash is not None and not isinstance(cell_content_hash, str):
        raise ValidationError(
            "body.cell_content_hash must be a string or null"
        )
    if result_snapshot_json is not None and not isinstance(
        result_snapshot_json, str
    ):
        raise ValidationError(
            "body.result_snapshot_json must be a string or null"
        )

    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_facts_service.pin_revision_fact(
            session,
            workspace_id=workspace_id,
            revision_uuid=revision_uuid,
            title=title,
            description_md=description_md,
            cell_content_hash=cell_content_hash,
            result_snapshot_json=result_snapshot_json,
            pinned_by_user_id=pinned_by_user_id,
        )
        envelope = notebook_facts_service.get_fact_detail(
            session, fact_uuid=row.fact_uuid
        )
        session.commit()
    # Best-effort feed fan-out — never blocks the originating write.
    _emit_pin_feed_event(
        request,
        envelope=envelope or {},
        workspace_id=workspace_id,
        actor_user_id=pinned_by_user_id,
    )
    logger.info(
        "notebook fact pinned: workspace=%s revision=%s cell=%s fact=%s",
        workspace_id,
        revision_uuid,
        cell_content_hash,
        envelope.get("fact_uuid") if envelope else None,
    )
    return JSONResponse(envelope or {}, status_code=201)


@router.get("/api/notebooks/facts")
async def api_list_facts(
    request: Request,
    notebook_path: str | None = Query(default=None),
    include_unpinned: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    """List facts in the active workspace, newest-pinned first.

    Args:
        request: Incoming request; any authenticated user.
        notebook_path: Optional notebook-path filter — restricts the
            list to facts whose revision lives under the given path.
        include_unpinned: When ``True``, soft-deleted rows are
            included for audit-grade browse.
        limit: 1–500 cap; default 50.

    Returns:
        JSON ``{"facts": [envelope, ...], "workspace_id": ...}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    notebook_id: str | None = None
    if notebook_path:
        notebook_id = _resolve_notebook_id(request, notebook_path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_facts_service.list_facts(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            include_unpinned=include_unpinned,
            limit=limit,
        )
        envelopes = [notebook_facts_service.row_to_envelope(r) for r in rows]
    return JSONResponse(
        {"workspace_id": workspace_id, "facts": envelopes}
    )


@router.get("/api/notebooks/facts/bulk")
async def api_list_facts_for_cells(
    request: Request,
    notebook_path: str = Query(...),
    cell_content_hashes: str = Query(
        default="",
        description="Comma-separated cell content_hash values",
    ),
) -> JSONResponse:
    """Bulk lookup of active cell-output facts for the editor's chip row.

    Args:
        request: Incoming request; any authenticated user.
        notebook_path: Relative notebook path.
        cell_content_hashes: Comma-separated list of cell
            ``content_hash`` strings.

    Returns:
        JSON ``{"facts": {<hash>: [envelope, ...]}}`` — hashes without
        a pinned fact are omitted.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    notebook_id = _resolve_notebook_id(request, notebook_path)
    hashes = [h.strip() for h in cell_content_hashes.split(",") if h.strip()]
    factory = request.app.state.session_factory
    with factory() as session:
        grouped = notebook_facts_service.list_facts_for_cells(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            cell_content_hashes=hashes,
        )
        out: dict[str, list[dict[str, Any]]] = {
            key: [notebook_facts_service.row_to_envelope(r) for r in rows]
            for key, rows in grouped.items()
        }
    return JSONResponse({"facts": out, "notebook_id": notebook_id})


@router.get("/api/notebooks/facts/{fact_uuid}")
async def api_get_fact(
    request: Request,
    fact_uuid: str,
) -> JSONResponse:
    """Return one fact's full envelope (with revision UUID + snapshot)."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_facts_service.get_fact_detail(
            session, fact_uuid=fact_uuid
        )
    if envelope is None:
        raise ValidationError(f"fact {fact_uuid!r} not found")
    if int(envelope.get("workspace_id") or 0) != int(workspace_id):
        # Hide cross-workspace facts behind a 404-style not-found
        # rather than 403 so a probe cannot enumerate UUIDs.
        raise ValidationError(f"fact {fact_uuid!r} not found")
    return JSONResponse(envelope)


@router.delete("/api/notebooks/facts/{fact_uuid}")
async def api_unpin_fact(
    request: Request,
    fact_uuid: str,
) -> JSONResponse:
    """Soft-delete a fact (stamp ``unpinned_at``)."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_facts_service.get_fact(session, fact_uuid=fact_uuid)
        if row is None or int(row.workspace_id) != int(workspace_id):
            raise ValidationError(f"fact {fact_uuid!r} not found")
        updated = notebook_facts_service.unpin_fact(
            session, fact_uuid=fact_uuid
        )
        envelope = notebook_facts_service.row_to_envelope(updated)
        session.commit()
    logger.info("notebook fact unpinned: %s", fact_uuid)
    return JSONResponse(envelope)


def _resolve_notebook_followers(
    session_factory: Any,
    *,
    workspace_id: int,
    notebook_id: str,
) -> list[int]:
    """Return user-ids subscribed to the parent notebook's social anchor.

    The pin's own entity_kind (``notebook_revision`` /
    ``notebook_cell_output``) carries an ephemeral fact UUID nobody
    would follow directly, so :func:`fanout_event` would resolve zero
    recipients on the polymorphic path.  Recipients should instead
    come from the notebook-level anchor (Phase 77.6 ``kind='notebook'``)
    — anyone who follows the notebook hears about its pins.  Returned
    as ``extra_recipients`` to :func:`fanout_event` so the actor-self
    filter still applies.
    """
    from sqlalchemy import select

    from pointlessql.models.social._social_follow import SocialFollow
    from pointlessql.models.social._social_target import SocialTarget

    with session_factory() as session:
        return [
            int(uid)
            for (uid,) in session.execute(
                select(SocialFollow.user_id)
                .join(
                    SocialTarget,
                    SocialTarget.id == SocialFollow.social_target_id,
                )
                .where(
                    SocialFollow.workspace_id == workspace_id,
                    SocialTarget.entity_kind == "notebook",
                    SocialTarget.entity_ref == notebook_id,
                )
            ).all()
        ]


def _emit_pin_feed_event(
    request: Request,
    *,
    envelope: dict[str, Any],
    workspace_id: int,
    actor_user_id: int | None,
) -> None:
    """Fan a ``notebook_revision_pinned`` event out to followers.

    Best-effort — failures are logged but never re-raised so the
    originating pin always completes.
    """
    try:
        from pointlessql.services.notifications.fanout import fanout_event

        fact_uuid = envelope.get("fact_uuid")
        notebook_id = envelope.get("notebook_id")
        cell_hash = envelope.get("cell_content_hash")
        title = envelope.get("title") or "(untitled fact)"
        if not fact_uuid:
            return
        kind = "notebook_cell_output" if cell_hash else "notebook_revision"
        source_url = f"/library/facts/{fact_uuid}"
        notebook_hint = (
            f"notebook ``{notebook_id}``" if notebook_id else "a notebook"
        )
        summary_md = f"Pinned **{title}** from {notebook_hint}"
        extra_recipients = (
            _resolve_notebook_followers(
                request.app.state.session_factory,
                workspace_id=workspace_id,
                notebook_id=notebook_id,
            )
            if notebook_id
            else []
        )
        fanout_event(
            request.app.state.session_factory,
            event_type="notebook_revision_pinned",
            entity_kind=kind,
            entity_ref=fact_uuid,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            source_url=source_url,
            summary_md=summary_md,
            extra_recipients=extra_recipients or None,
        )
    except Exception:  # noqa: BLE001 — fanout is best-effort
        logger.exception(
            "feed fan-out for notebook_revision_pinned failed"
        )


@router.get("/library/facts", response_class=HTMLResponse)
async def page_facts_library(request: Request) -> HTMLResponse:
    """Render the workspace's pinned-facts library browse page.

    The page itself is a thin shell — the actual fact list is fetched
    client-side via ``GET /api/notebooks/facts`` so the page renders
    fast even when the workspace has hundreds of facts.

    Args:
        request: Incoming FastAPI request; any authenticated user.

    Returns:
        Rendered ``pages/library_facts.html`` template.
    """
    require_user(request)
    return templates(request).TemplateResponse(
        request,
        "pages/library_facts.html",
        {
            "active_page": "library",
        },
    )
