"""Notebook document I/O: load / save / cell history / markdown render."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import AuthorizationError, ValidationError
from pointlessql.models import NotebookCellProposal, NotebookCellProvenance
from pointlessql.models.notebook import NotebookCellIdentity
from pointlessql.services import output_rendering as notebook_render_service
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import cell_authorship as cell_authorship_service
from pointlessql.services.notebook import cell_reconciliation
from pointlessql.services.notebook import outputs as notebook_outputs_service
from pointlessql.services.notebook import permissions as notebook_permissions_service


def _enforce_notebook_role(
    request: Request, *, notebook_id: str, required: str
) -> None:
    """Reject the request when the actor's effective role is below *required*.

    wires the existing ``role_satisfies`` lattice
    into the load / save paths so explicit grants narrow workspace-
    default access.  Notebooks with no explicit grants behave like
    they always did (any authenticated user can view + run + save —
    only ``edit`` becomes per-notebook restrictable today; this
    matches the existing test-suite expectations).

    Args:
        request: Incoming request; ``request.state.user`` must be set
            by the auth middleware.
        notebook_id: Stable notebook UUID.
        required: One of ``view`` / ``run`` / ``edit``.

    Raises:
        AuthorizationError: When the user lacks the role.
    """
    user = getattr(request.state, "user", None) or {}
    user_id = int(user.get("id") or 0)
    is_admin = bool(user.get("is_admin"))
    factory = request.app.state.session_factory
    with factory() as session:
        allowed = notebook_permissions_service.actor_has_role(
            session,
            notebook_id=notebook_id,
            user_id=user_id,
            is_admin=is_admin,
            required=required,
        )
    if not allowed:
        raise AuthorizationError(
            principal=str(user.get("email") or "(anonymous)"),
            privilege=required,
            securable_type="notebook",
            full_name=notebook_id,
        )

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/load")
async def api_load_notebook(request: Request, path: str) -> JSONResponse:
    """Load a ``.py`` notebook + its persisted outputs.

    The browser editor calls this on page-mount.  Returns the cell list
    (with content_hashes) plus every persisted output frame keyed by
    ``(content_hash, kernel_session_id)``.  Re-render cost on a page
    reload stays close to free — kernel-message replay happens
    client-side from the embedded JSON, no extra fetch.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        JSON ``{path, dirty, cells: [...], outputs: [...]}``.
        Each cell carries ``id`` (transient ordinal), ``content_hash``,
        ``cell_type``, ``source``, ``result_var``.  Each output carries
        ``content_hash``, ``kernel_session_id``, ``output_index``,
        ``msg_type``, ``content``, ``metadata``, ``created_at``.

    Raises:
        ValidationError: When the path is missing / outside the
            workspace / wrong suffix / does not exist.  Surfaces
            via :func:`resolve_py_notebook_path`.
    """  # noqa: DOC502
    require_user(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    document = notebook_doc_service.load_document(absolute, relative)
    outputs = notebook_outputs_service.load_outputs_for_path(
        request.app.state.session_factory, relative
    )
    cell_uuids = _load_cell_uuid_map(request, relative)
    notebook_uuid = cell_uuids.get("__notebook__")
    if notebook_uuid:
        _enforce_notebook_role(
            request, notebook_id=notebook_uuid, required="view"
        )
    cells = [
        {
            "id": cell.id,
            "content_hash": cell.content_hash,
            "cell_uuid": cell_uuids.get(cell.content_hash),
            "cell_type": cell.cell_type,
            "source": cell.source,
            "result_var": cell.result_var,
            "tags": list(cell.tags),
        }
        for cell in document.cells
    ]
    return JSONResponse(
        {
            "path": document.path,
            "dirty": document.dirty,
            "mtime": absolute.stat().st_mtime,
            "notebook_uuid": notebook_uuid,
            "cells": cells,
            "outputs": outputs,
        }
    )


def _load_cell_uuid_map(request: Request, file_path: str) -> dict[str, str | None]:
    """Return ``content_hash -> cell_uuid`` for the load path.

    The result also carries the parent notebook UUID under the
    sentinel key ``"__notebook__"`` so the caller doesn't have to look
    it up twice.  Cells in the file that have no matching live row in
    ``notebook_cells`` (e.g. brand-new notebook never saved since
    Phase 95 landed) return ``None`` for their UUID; the next save
    mints them.
    """
    notebook_uuid = get_or_create_notebook_uuid(request, file_path)
    factory = request.app.state.session_factory
    mapping: dict[str, str | None] = {"__notebook__": notebook_uuid}
    with factory() as session:
        rows = session.execute(
            select(
                NotebookCellIdentity.id,
                NotebookCellIdentity.current_content_hash,
            ).where(
                NotebookCellIdentity.notebook_id == notebook_uuid,
                NotebookCellIdentity.removed_at.is_(None),
            )
        ).all()
    for row in rows:
        mapping[row[1]] = row[0]
    return mapping


@router.post("/api/notebooks/save")
async def api_save_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Persist a notebook's cells back to disk.

    The browser editor sends ``{path, cells, expected_mtime?}``;
    cells are an ordered list of ``{cell_type, source, result_var?}``
    dicts.  When ``expected_mtime`` is supplied and disagrees with
    the current on-disk mtime, the route 409s with
    ``{"error": "mtime_conflict", "current_mtime": <iso>}`` so the
    browser can prompt the user to reload before overwriting.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        body: JSON body with ``path``, ``cells``, optional
            ``expected_mtime`` (float seconds since epoch).

    Returns:
        JSON ``{path, mtime, cells: [{content_hash, ...}]}`` on
        success — cells carry the freshly-computed FNV-1a-64
        content_hashes so the browser can clear ``_dirty`` flags.

    Raises:
        ValidationError: When path / cells are malformed or escape
            the workspace root.
    """
    require_user(request)
    raw_path = body.get("path") if isinstance(body, dict) else None
    raw_cells = body.get("cells") if isinstance(body, dict) else None
    if not isinstance(raw_path, str):
        raise ValidationError("body.path must be a string")
    if not isinstance(raw_cells, list):
        raise ValidationError("body.cells must be a list")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, raw_path, must_exist=True
    )
    expected_mtime = body.get("expected_mtime")
    if isinstance(expected_mtime, (int, float)):
        current_mtime = absolute.stat().st_mtime
        if abs(current_mtime - float(expected_mtime)) > 0.001:
            # Return JSONResponse directly so the structured 409 body
            # survives the central error handler's str-coercion of
            # HTTPException.detail.
            return JSONResponse(
                {
                    "error": "mtime_conflict",
                    "current_mtime": current_mtime,
                },
                status_code=409,
            )
    cells: list[notebook_doc_service.NotebookCell] = []
    # collect optional client-provided cell_uuids in the
    # same order as the input cells.  The save-barrier compares them
    # against the reconciler's output to emit a CRDT remap advisory
    # for any cell whose canonical UUID changed (e.g. Pass-3 mint).
    client_cell_uuids: list[str | None] = []
    for index, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise ValidationError(
                f"body.cells[{index}] must be an object, got {type(raw).__name__}"
            )
        cell_type = raw.get("cell_type", "code")
        if cell_type not in {"code", "markdown", "sql"}:
            raise ValidationError(
                f"body.cells[{index}].cell_type must be one of code/markdown/sql"
            )
        source = raw.get("source", "")
        if not isinstance(source, str):
            raise ValidationError(
                f"body.cells[{index}].source must be a string"
            )
        result_var = raw.get("result_var")
        if result_var is not None and not isinstance(result_var, str):
            raise ValidationError(
                f"body.cells[{index}].result_var must be a string or null"
            )
        raw_tags = raw.get("tags") or []
        if not isinstance(raw_tags, list):
            raise ValidationError(
                f"body.cells[{index}].tags must be a list of strings"
            )
        tags: tuple[str, ...] = tuple(
            t for t in raw_tags if isinstance(t, str) and t
        )
        raw_cell_uuid = raw.get("cell_uuid")
        if raw_cell_uuid is not None and not isinstance(raw_cell_uuid, str):
            raise ValidationError(
                f"body.cells[{index}].cell_uuid must be a string or null"
            )
        client_cell_uuids.append(raw_cell_uuid if raw_cell_uuid else None)
        cells.append(
            notebook_doc_service.NotebookCell(
                id=f"cell-{index}",
                content_hash=notebook_doc_service.compute_content_hash(source),
                cell_type=cell_type,
                source=source,
                result_var=result_var if cell_type == "sql" else None,
                tags=tags,
            )
        )
    # enforce edit-role before persisting.  We
    # resolve the notebook UUID *before* the file write so an
    # unauthorised caller can't mutate disk and then bounce on the
    # gate.  ``get_or_create_notebook_uuid`` is idempotent so the
    # double call is cheap.
    relative_for_check = str(absolute.relative_to(notebooks_dir))
    pre_notebook_uuid = get_or_create_notebook_uuid(request, relative_for_check)
    _enforce_notebook_role(
        request, notebook_id=pre_notebook_uuid, required="edit"
    )
    notebook_doc_service.save_document(absolute, cells)
    new_mtime = absolute.stat().st_mtime
    relative = str(absolute.relative_to(notebooks_dir))
    notebook_uuid = get_or_create_notebook_uuid(request, relative)
    workspace_id = current_workspace_id(request)
    reconcile_inputs = [
        cell_reconciliation.ReconcileInput(
            content_hash=cell.content_hash, source=cell.source
        )
        for cell in cells
    ]
    raw_acceptances = body.get("proposal_acceptances")
    proposal_acceptances: list[dict[str, Any]] = []
    if isinstance(raw_acceptances, list):
        for raw_acc in raw_acceptances:
            if not isinstance(raw_acc, dict):
                continue
            proposal_acceptances.append(dict(raw_acc))
    factory = request.app.state.session_factory
    with factory() as session:
        results = cell_reconciliation.reconcile(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_uuid,
            new_cells=reconcile_inputs,
        )
        if proposal_acceptances:
            _write_proposal_provenance(
                session,
                proposal_acceptances=proposal_acceptances,
                reconcile_results=results,
            )
        # upsert per-cell authorship for every reconciled
        # cell so the editor's cell-header chip can render "minted by
        # X • last edited by Y".  The reconciler returned a UUID per
        # input cell; pair them with the saver's identity here.
        actor_email = ""
        try:
            actor_email = str(
                request.state.user.get("email") or ""
            ) if request.state.user else ""
        except AttributeError:
            actor_email = ""
        if actor_email:
            for res in results:
                try:
                    cell_authorship_service.upsert_cell_authorship(
                        session,
                        cell_uuid=res.cell_id,
                        kind="user",
                        email=actor_email,
                    )
                except Exception:  # noqa: BLE001 — non-fatal
                    logger.exception(
                        "phase101 authorship upsert failed for cell %s",
                        res.cell_id,
                    )
        session.commit()
    out_cells = [
        {
            "id": cell.id,
            "content_hash": cell.content_hash,
            "cell_uuid": results[index].cell_id,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "result_var": cell.result_var,
            "tags": list(cell.tags),
        }
        for index, cell in enumerate(cells)
    ]
    # if the reconciler minted a different UUID than the
    # client tracked, broadcast a remap so every open browser tab
    # patches its Y.Doc + Alpine state in lock-step.  No-op when no
    # client uuids were sent (older clients, pre-105.3 callers) or
    # when no hub is open.
    remap: dict[str, str] = {}
    for client_uuid, result in zip(client_cell_uuids, results, strict=True):
        if client_uuid is None:
            continue
        if client_uuid == result.cell_id:
            continue
        remap[client_uuid] = result.cell_id
    if remap:
        try:
            await notebook_coedit_ws.apply_save_remap(notebook_uuid, remap)
        except Exception:  # noqa: BLE001 — non-fatal best-effort
            logger.exception(
                "phase105.5 cell_uuid remap broadcast failed for %s", notebook_uuid
            )
    logger.info("saved notebook %s (%d cells)", relative, len(cells))
    return JSONResponse(
        {
            "path": relative,
            "mtime": new_mtime,
            "notebook_uuid": notebook_uuid,
            "cells": out_cells,
        }
    )


@router.get("/api/notebooks/cell-history")
async def api_cell_history(
    request: Request,
    path: str = Query(..., min_length=1),
    content_hash: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    """Return the last *limit* run-source rows for one cell.

    Backs the per-cell run-history popover the notebook editor
    surfaces in Sprint 66.7.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.
        content_hash: FNV-1a-64 cell identity.
        limit: Maximum rows to return (1-100, default 20).

    Returns:
        JSON ``{"cell": {"path", "content_hash"}, "runs": [...]}``.
        Each run row carries ``id`` / ``execution_count`` / ``source``
        / ``started_at`` / ``finished_at`` / ``status`` /
        ``kernel_session_id``.
    """
    require_user(request)
    runs = notebook_outputs_service.list_cell_run_sources(
        request.app.state.session_factory,
        file_path=path,
        content_hash=content_hash,
        limit=limit,
    )
    return JSONResponse(
        {
            "cell": {"path": path, "content_hash": content_hash},
            "runs": runs,
        }
    )


@router.post("/api/notebooks/render-markdown")
async def api_render_markdown(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Render a markdown cell to sanitised HTML.

    Server-side render via the existing markdown-it-py CommonMark
    renderer (HTML disabled in the parser → embedded
    ``<script>`` / ``<iframe>`` tags are escaped at parse time).

    Args:
        request: Incoming FastAPI request; any authenticated user.
        body: JSON body with key ``source`` (markdown text).

    Returns:
        JSON ``{"html": "<rendered fragment>"}``.

    Raises:
        ValidationError: When ``body.source`` is missing / non-string.
    """
    require_user(request)
    raw = body.get("source") if isinstance(body, dict) else None
    if not isinstance(raw, str):
        raise ValidationError("body.source must be a string")
    html = notebook_render_service.render_markdown_source(raw)
    return JSONResponse({"html": html})


def _write_proposal_provenance(
    session: Any,
    *,
    proposal_acceptances: list[dict[str, Any]],
    reconcile_results: list[cell_reconciliation.ReconcileResult],
) -> None:
    """Flush accepted-proposal records into :class:`NotebookCellProvenance`.

    Called from the save-route inside the reconcile transaction so
    the new identity rows the reconciler just minted are visible.

    Acceptance entries are dicts with shape::

        {
          "proposal_id": str,
          "action": "propose" | "fix",
          "agent_run_id": str,
          "placeholder_index": int,   # for action='propose'
          "target_cell_uuid": str,    # for action='fix'
        }

    For ``propose`` the frontend tracks the new cell's position in
    the saved cells array via ``placeholder_index``; we map that to
    the reconciler's final cell_uuid.  For ``fix`` the target uuid is
    already known.  Explain proposals don't ride this path — they
    write their provenance row inline at create-time.

    Args:
        session: Active SQLAlchemy session (do not commit; the
            caller owns the transaction).
        proposal_acceptances: List of acceptance dicts (see above).
        reconcile_results: Output of
            :func:`cell_reconciliation.reconcile` for the current
            save — same order as the cells list.
    """
    now = datetime.datetime.now(datetime.UTC)
    for acc in proposal_acceptances:
        action = acc.get("action")
        proposal_id = acc.get("proposal_id")
        agent_run_id = acc.get("agent_run_id")
        if not isinstance(proposal_id, str) or not isinstance(agent_run_id, str):
            continue
        if action == "propose":
            placeholder_index = acc.get("placeholder_index")
            if not isinstance(placeholder_index, int):
                continue
            if not 0 <= placeholder_index < len(reconcile_results):
                continue
            cell_uuid = reconcile_results[placeholder_index].cell_id
        elif action == "fix":
            cell_uuid = acc.get("target_cell_uuid")
            if not isinstance(cell_uuid, str):
                continue
        else:
            continue
        session.add(
            NotebookCellProvenance(
                cell_uuid=cell_uuid,
                agent_run_id=agent_run_id,
                proposal_id=proposal_id,
                action=action,
                created_at=now,
            )
        )
        # Mirror the final cell_uuid back onto the proposal row so
        # audit queries don't need to JOIN the provenance table.
        proposal = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one_or_none()
        )
        if proposal is not None:
            proposal.inserted_cell_uuid = cell_uuid
        # AI-acceptance authorship (Wave-B follow-up
        # 2026-05-20).  Fires BEFORE the save-handler's user-authorship
        # loop so the row's ``first_author_*`` gets the agent and the
        # user-loop only bumps ``last_modifier_*`` to the saver.  Net
        # effect: the chip reads "minted by AI • last edit by Flo".
        # Inline editor chat has no registered ``Agent`` DB row;
        # ``agent_id`` stays None and the service contract accepts
        # ``agent_run_id``-only attribution.
        try:
            cell_authorship_service.upsert_cell_authorship(
                session,
                cell_uuid=cell_uuid,
                kind="agent",
                agent_run_id=agent_run_id,
            )
        except Exception:  # noqa: BLE001 — non-fatal
            logger.exception(
                "phase101 agent authorship upsert failed for cell %s",
                cell_uuid,
            )
