"""WebSocket endpoint: ``/ws/notebook/kernel?path=...``."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pointlessql.api.notebook_kernel_ws._handlers import (
    handle_execute,
    handle_interrupt,
    handle_restart,
)
from pointlessql.api.notebook_kernel_ws._protocol import (
    send_error,
    user_can_use_editor,
)
from pointlessql.api.notebook_kernel_ws._pump import pump_subscription
from pointlessql.api.ws_auth import resolve_websocket_user as _resolve_websocket_user
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc
from pointlessql.services.notebook.kernel_session import KernelRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebook-kernel-ws"])


@router.websocket("/ws/notebook/kernel")
async def notebook_kernel_ws(websocket: WebSocket) -> None:
    """Bridge browser-side cell execution to the per-notebook kernel.

    Query parameters:
        path: Relative notebook path under ``notebooks_dir``.

    Sequence:

    1. Resolve user from cookie or Bearer; close 4401 / 4403 on miss.
    2. Resolve + validate the notebook path; close 4404 on bad path.
    3. Get-or-start the kernel via ``app.state.kernel_registry``.
    4. Subscribe to iopub + shell channels; spawn pump tasks.
    5. Read inbound frames in a loop; dispatch to per-method handlers.
    6. On disconnect: unsubscribe, cancel pump tasks (kernel survives
       so a reconnect from the same user reuses session + outputs).
    """
    raw_path = websocket.query_params.get("path", "")
    user = _resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    if not user_can_use_editor(user):
        await websocket.close(code=4403)
        return
    settings: Settings = websocket.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    try:
        absolute = notebook_doc.resolve_py_notebook_path(
            notebooks_dir,
            raw_path,
            must_exist=True,
        )
    except ValidationError:
        await websocket.close(code=4404)
        return
    relative_path = str(absolute.relative_to(notebooks_dir))
    registry: KernelRegistry | None = getattr(websocket.app.state, "kernel_registry", None)
    if registry is None:
        await websocket.close(code=4503)
        return
    user_id = int(user.get("id") or 0)
    user_email = str(user.get("email") or "")
    is_admin = bool(user.get("is_admin"))
    # resolve notebook UUID + active branch
    # binding so the kernel session sees them as env vars at startup.
    # Falls back gracefully (None) on cold notebooks that haven't
    # been minted a UUID yet — the kernel just runs against main.
    factory_for_lookup = websocket.app.state.session_factory
    notebook_id: str | None = None
    branch_name: str | None = None
    try:
        with factory_for_lookup() as _session:
            from pointlessql.models.notebook import Notebook as _NotebookModel
            from pointlessql.services.notebook import (
                branch_bindings as _branch_bindings_service,
            )
            from pointlessql.services.notebook import (
                permissions as _notebook_permissions_service,
            )

            row = _session.query(_NotebookModel).filter_by(file_path=relative_path).one_or_none()
            if row is not None:
                notebook_id = row.id
                binding = _branch_bindings_service.get_current_binding(_session, notebook_id=row.id)
                if binding:
                    branch_name = binding.get("branch_name")
                # gate the WS at open time on the
                # ``run`` role.  Explicit ``view``-only grants block
                # the kernel from starting for this user; admins +
                # un-granted (workspace-default) callers pass.
                if not _notebook_permissions_service.actor_has_role(
                    _session,
                    notebook_id=row.id,
                    user_id=user_id,
                    is_admin=is_admin,
                    required="run",
                ):
                    await websocket.close(code=4403)
                    return
    except Exception:  # noqa: BLE001
        logger.exception("kernel context resolve failed; running against main")
    workspace_id = int(getattr(websocket.state, "workspace_id", 0) or 0) or 1
    session = await registry.get_or_start(
        user_id,
        user_email,
        relative_path,
        notebook_id=notebook_id,
        branch_name=branch_name,
        workspace_id=workspace_id,
    )
    factory = websocket.app.state.session_factory
    await websocket.accept()
    sub = session.subscribe()
    pending_run_sources: dict[tuple[str, str], int] = {}
    output_counters: dict[tuple[str, str], int] = {}
    sql_cell_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    cell_run_started_at: dict[tuple[str, str], datetime.datetime] = {}
    iopub_task = asyncio.create_task(
        pump_subscription(
            websocket,
            sub,
            file_path=relative_path,
            session=session,
            factory=factory,
            pending_run_sources=pending_run_sources,
            output_counters=output_counters,
            sql_cell_metadata=sql_cell_metadata,
            user=user,
            workspace_id=workspace_id,
            cell_run_started_at=cell_run_started_at,
            channel="iopub",
        ),
        name=f"ws-iopub-{session.session_id[:8]}",
    )
    shell_task = asyncio.create_task(
        pump_subscription(
            websocket,
            sub,
            file_path=relative_path,
            session=session,
            factory=factory,
            pending_run_sources=pending_run_sources,
            output_counters=output_counters,
            sql_cell_metadata=sql_cell_metadata,
            user=user,
            workspace_id=workspace_id,
            cell_run_started_at=cell_run_started_at,
            channel="shell",
        ),
        name=f"ws-shell-{session.session_id[:8]}",
    )
    await websocket.send_text(
        json.dumps(
            {
                "notify": "ready",
                "params": {
                    "kernel_session_id": session.session_id,
                    "path": relative_path,
                },
            }
        )
    )
    try:
        while True:
            text = await websocket.receive_text()
            try:
                frame = json.loads(text)
            except json.JSONDecodeError:
                await send_error(
                    websocket,
                    request_id=None,
                    code="bad_json",
                    message="frame was not valid JSON",
                )
                continue
            if not isinstance(frame, dict):
                await send_error(
                    websocket,
                    request_id=None,
                    code="bad_frame",
                    message="frame must be a JSON object",
                )
                continue
            request_id_raw = frame.get("id")
            request_id = int(request_id_raw) if isinstance(request_id_raw, int) else None
            method = frame.get("method")
            params = frame.get("params") or {}
            if not isinstance(params, dict):
                await send_error(
                    websocket,
                    request_id=request_id,
                    code="bad_frame",
                    message="params must be a JSON object",
                )
                continue
            if method == "execute":
                await handle_execute(
                    websocket,
                    request_id=request_id,
                    params=params,
                    file_path=relative_path,
                    session=session,
                    factory=factory,
                    pending_run_sources=pending_run_sources,
                    output_counters=output_counters,
                    sql_cell_metadata=sql_cell_metadata,
                    cell_run_started_at=cell_run_started_at,
                    user=user,
                )
            elif method == "interrupt":
                await handle_interrupt(
                    websocket,
                    request_id=request_id,
                    session=session,
                )
            elif method == "restart":
                await handle_restart(
                    websocket,
                    request_id=request_id,
                    session=session,
                    file_path=relative_path,
                    factory=factory,
                    pending_run_sources=pending_run_sources,
                    output_counters=output_counters,
                )
            else:
                await send_error(
                    websocket,
                    request_id=request_id,
                    code="unknown_method",
                    message=f"unknown method {method!r}",
                )
    except WebSocketDisconnect:
        pass
    finally:
        for task in (iopub_task, shell_task):
            if not task.done():
                task.cancel()
        session.unsubscribe(sub)
