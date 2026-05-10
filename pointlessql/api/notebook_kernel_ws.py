"""WebSocket route bridging browser cells to per-notebook ipykernel subprocesses.

Phase 66.0 reintroduction.  The Phase-12 ``notebook_kernel_ws.py`` was
deleted in the agent-first pivot; this rebuild keeps every load-bearing
piece (``KernelRegistry``, ``KernelSession``, ``notebook_outputs``
persistence, content-hash cell identity) and replaces the deleted
WebSocket layer with a smaller JSON-RPC-shaped surface:

* Inbound frames: ``{"id": <int>, "method": <str>, "params": {...}}``
  with ``method ∈ {"execute", "interrupt", "restart"}``.
* Outbound replies: ``{"id": <int>, "result": {...}}`` or
  ``{"id": <int>, "error": {"code": <str>, "message": <str>}}``.
* Outbound notifications: ``{"notify": "kernel_message", "params":
  {"channel": "iopub"|"shell", "msg_type": ..., "content_hash": ...,
  "content": ..., "metadata": ..., "parent_msg_id": ...}}``.

Maps 1:1 onto the underlying jupyter_client wire spec so a future
client can be a thin shim over the upstream Jupyter Messaging Spec
without introducing a PointlesSQL-specific protocol.

Auth is independent of ``auth_middleware`` because Starlette's
HTTP middleware does not run for WebSocket upgrades — the helper
:func:`_resolve_websocket_user` re-runs the cookie + Bearer-key
hop the middleware does for HTTP requests.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pointlessql.config import Settings
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogNotFoundError,
    ValidationError,
)
from pointlessql.pql import SQLParseError
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import auth as auth_service
from pointlessql.services import query_history as query_history_service
from pointlessql.services.notebook import _doc as notebook_doc
from pointlessql.services.notebook import _sql_cell as notebook_sql_cell
from pointlessql.services.notebook import outputs as notebook_outputs_service
from pointlessql.services.notebook.kernel_session import (
    KernelMessage,
    KernelRegistry,
    KernelSession,
    Subscription,
    drain,
)
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebook-kernel-ws"])

_RESERVED_BOOTSTRAP_HASH = "__pql_sql_bootstrap__"


def _resolve_websocket_user(websocket: WebSocket) -> UserInfo | None:
    """Re-run cookie + Bearer auth for a WebSocket upgrade.

    Starlette's ``BaseHTTPMiddleware``-style ``auth_middleware`` does
    not run for WebSocket scope, so we mirror its two attempts here:

    1. ``pql_session`` cookie → JWT verification → :class:`UserInfo`.
    2. ``Authorization: Bearer ...`` header → DB-backed api_keys
       verification → synthetic :class:`UserInfo` carrying the key
       name and scope flags.

    Args:
        websocket: The incoming WebSocket connection.

    Returns:
        The resolved :class:`UserInfo` or ``None`` if neither path
        produced an identity.
    """
    factory = getattr(websocket.app.state, "session_factory", None)
    settings = getattr(websocket.app.state, "settings", None)
    if factory is None or settings is None:
        return None
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if token is not None:
        user = auth_service.get_current_user(
            factory,
            token,
            settings.auth.secret_key,
            previous_key=settings.auth.secret_key_previous,
        )
        if user is not None:
            return user
    entry = api_keys_service.verify_bearer(
        websocket.headers.get("authorization"),
        factory,
    )
    if entry is None:
        return None
    return UserInfo(
        id=0,
        email=f"api_key:{entry.name}",
        display_name=entry.name,
        is_admin=False,
        is_supervisor=entry.supervisor,
        is_auditor=entry.auditor,
    )


def _user_can_use_editor(user: UserInfo) -> bool:
    """Return whether the resolved user is permitted to drive the editor.

    Phase 66.0 keeps the gate at admin-or-auditor parity with the
    read-only workspace page; future sprints can broaden once the
    workspace-membership model lands a ``notebook_author`` role.
    """
    return bool(user.get("is_admin") or user.get("is_auditor"))


async def _send_error(
    websocket: WebSocket,
    *,
    request_id: int | None,
    code: str,
    message: str,
) -> None:
    """Send a JSON-RPC error frame for a specific inbound request id.

    Args:
        websocket: The active WebSocket.
        request_id: Original ``id`` from the request frame, or
            ``None`` when the failing input never produced one.
        code: Short identifier — caller-actionable, mirrors the
            upstream Jupyter convention.
        message: One-sentence human-readable detail.
    """
    payload: dict[str, Any] = {
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    try:
        await websocket.send_text(json.dumps(payload))
    except WebSocketDisconnect:
        return


async def _pump_subscription(
    websocket: WebSocket,
    sub: Subscription,
    *,
    file_path: str,
    session: KernelSession,
    factory: Any,
    pending_run_sources: dict[tuple[str, str], int],
    output_counters: dict[tuple[str, str], int],
    sql_cell_metadata: dict[tuple[str, str], dict[str, Any]],
    user: UserInfo,
    workspace_id: int,
    cell_run_started_at: dict[tuple[str, str], datetime.datetime],
    channel: str,
) -> None:
    """Forward one ZMQ channel's messages from kernel queue to the browser.

    Mirrors the persistence side-effect the deleted Phase-12 handler
    had: every ``stream`` / ``execute_result`` / ``display_data`` /
    ``error`` iopub frame lands in ``notebook_outputs`` so a page
    reload can replay the cell view without re-executing.

    Args:
        websocket: Outbound WebSocket connection.
        sub: Subscription handle from
            :meth:`KernelSession.subscribe`.
        file_path: Notebook path (relative).
        session: The owning :class:`KernelSession`.
        factory: SQLAlchemy session factory.
        pending_run_sources: Map ``(content_hash,
            kernel_session_id) -> run_source_id`` so an
            ``execute_reply`` on the shell channel can stamp the
            matching run-source's finish columns.
        output_counters: Per-cell monotonic counter feeding
            ``notebook_outputs.output_index``.  Lives across both
            channels so we can mutate it from this single helper.
        sql_cell_metadata: Map keyed by ``(content_hash,
            kernel_session_id)`` carrying ``raw_sql`` +
            ``approved_tables`` for SQL cells so the execute_reply
            handler can write a ``query_history`` row.
        user: Authenticated user driving the WebSocket — copied
            into the audit row's ``user_id`` / ``user_email``.
        workspace_id: Active workspace from auth_middleware,
            recorded on the ``query_history`` row for tenant
            isolation.
        cell_run_started_at: Map keyed by ``(content_hash,
            kernel_session_id)`` to ``execute_request`` start
            time; the ``execute_reply`` handler subtracts to
            compute ``duration_ms``.
        channel: ``"iopub"`` or ``"shell"`` — selects which queue we
            drain.
    """
    queue = sub.iopub if channel == "iopub" else sub.shell
    async for msg in drain(queue):
        try:
            await _handle_kernel_message(
                websocket,
                msg,
                file_path=file_path,
                session=session,
                factory=factory,
                pending_run_sources=pending_run_sources,
                output_counters=output_counters,
                sql_cell_metadata=sql_cell_metadata,
                user=user,
                workspace_id=workspace_id,
                cell_run_started_at=cell_run_started_at,
                channel=channel,
            )
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001 — keep the pump alive on transient errors
            logger.exception("kernel pump frame handling failed")


async def _handle_kernel_message(
    websocket: WebSocket,
    msg: KernelMessage,
    *,
    file_path: str,
    session: KernelSession,
    factory: Any,
    pending_run_sources: dict[tuple[str, str], int],
    output_counters: dict[tuple[str, str], int],
    sql_cell_metadata: dict[tuple[str, str], dict[str, Any]],
    user: UserInfo,
    workspace_id: int,
    cell_run_started_at: dict[tuple[str, str], datetime.datetime],
    channel: str,
) -> None:
    """Process one :class:`KernelMessage` — persist + forward."""
    if msg.content_hash == _RESERVED_BOOTSTRAP_HASH:
        # Skip bootstrap echoes — the helper definition is internal.
        return
    if (
        channel == "iopub"
        and msg.content_hash is not None
        and notebook_outputs_service.is_persistable(msg.msg_type)
    ):
        key = (msg.content_hash, session.session_id)
        index = output_counters.get(key, 0)
        output_counters[key] = index + 1
        try:
            notebook_outputs_service.append_output(
                factory,
                file_path=file_path,
                content_hash=msg.content_hash,
                kernel_session_id=session.session_id,
                output_index=index,
                msg_type=msg.msg_type,
                content=msg.content,
                metadata=msg.metadata or None,
            )
        except Exception:  # noqa: BLE001 — persistence must not break the pump
            logger.exception("notebook_outputs append failed")
    if (
        channel == "shell"
        and msg.msg_type == "execute_reply"
        and msg.content_hash is not None
    ):
        status = str(msg.content.get("status", "ok"))
        execution_count_raw = msg.content.get("execution_count")
        execution_count = (
            int(execution_count_raw) if isinstance(execution_count_raw, int) else None
        )
        finished_at = datetime.datetime.now(datetime.UTC)
        try:
            notebook_outputs_service.upsert_cell_run(
                factory,
                file_path=file_path,
                content_hash=msg.content_hash,
                kernel_session_id=session.session_id,
                status=status,
                execution_count=execution_count,
                finished=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("notebook_cell_run upsert (finish) failed")
        run_source_id = pending_run_sources.pop(
            (msg.content_hash, session.session_id), None
        )
        if run_source_id is not None:
            try:
                notebook_outputs_service.record_cell_run_finish(
                    factory,
                    source_id=run_source_id,
                    status=status,
                    execution_count=execution_count,
                    finished_at=finished_at,
                )
            except Exception:  # noqa: BLE001
                logger.exception("notebook_cell_run_source finish failed")
        # SQL-cell audit row.  Only writes when the cell was wrapped
        # via __pql_sql_run; pure-Python cells never enter this path.
        sql_meta = sql_cell_metadata.pop(
            (msg.content_hash, session.session_id), None
        )
        if sql_meta is not None:
            started_at = cell_run_started_at.pop(
                (msg.content_hash, session.session_id), finished_at
            )
            duration_ms = max(
                0,
                int((finished_at - started_at).total_seconds() * 1000),
            )
            try:
                query_history_service.record_query(
                    factory,
                    user_id=int(user.get("id") or 0),
                    user_email=str(user.get("email") or ""),
                    sql_text=str(sql_meta.get("raw_sql") or ""),
                    started_at=started_at,
                    finished_at=finished_at,
                    status="succeeded" if status == "ok" else "failed",
                    row_count=None,
                    duration_ms=duration_ms,
                    referenced_tables=list(
                        sql_meta.get("approved_tables") or []
                    ),
                    workspace_id=workspace_id,
                    notebook_path=file_path,
                    notebook_content_hash=msg.content_hash,
                )
            except Exception:  # noqa: BLE001
                logger.exception("query_history record_query failed")
    payload = {
        "notify": "kernel_message",
        "params": {
            "channel": channel,
            "msg_type": msg.msg_type,
            "content_hash": msg.content_hash,
            "content": msg.content,
            "metadata": msg.metadata,
            "parent_msg_id": msg.parent_msg_id,
        },
    }
    await websocket.send_text(json.dumps(payload))


async def _handle_execute(
    websocket: WebSocket,
    *,
    request_id: int | None,
    params: dict[str, Any],
    file_path: str,
    session: KernelSession,
    factory: Any,
    pending_run_sources: dict[tuple[str, str], int],
    output_counters: dict[tuple[str, str], int],
    sql_cell_metadata: dict[tuple[str, str], dict[str, Any]],
    cell_run_started_at: dict[tuple[str, str], datetime.datetime],
    user: UserInfo,
) -> None:
    """Handle a JSON-RPC ``execute`` request.

    Persists a fresh ``notebook_cell_run_sources`` row before sending
    the kernel ``execute_request`` so the run-history popover (Sprint
    66.7) sees a row even if the kernel hangs and never replies.
    SQL cells (``cell_type == 'sql'``) get their source wrapped with
    a call to the kernel-bootstrap ``__pql_sql_run`` helper after a
    server-side privilege check resolves the ``approved_tables`` map.
    """
    content_hash = params.get("content_hash")
    source = params.get("source")
    if not isinstance(content_hash, str) or not content_hash.strip():
        await _send_error(
            websocket,
            request_id=request_id,
            code="bad_params",
            message="execute params.content_hash must be a non-empty string",
        )
        return
    if not isinstance(source, str):
        await _send_error(
            websocket,
            request_id=request_id,
            code="bad_params",
            message="execute params.source must be a string",
        )
        return
    cell_type = params.get("cell_type") or "code"
    result_var = params.get("result_var")
    if not isinstance(cell_type, str):
        cell_type = "code"
    if cell_type == "sql":
        # SQL cells: wrap server-side with __pql_sql_run after a
        # privilege check on every referenced table.  The browser
        # never sees the approved_tables map.
        try:
            uc_client = websocket.app.state.uc_client
            approved = await notebook_sql_cell.resolve_approved_tables(
                source,
                uc_client=uc_client,
                actor_email=str(user.get("email") or ""),
                is_admin=bool(user.get("is_admin")),
            )
        except SQLParseError as exc:
            await _send_error(
                websocket,
                request_id=request_id,
                code="sql_parse_error",
                message=str(exc),
            )
            return
        except AuthorizationError as exc:
            await _send_error(
                websocket,
                request_id=request_id,
                code="sql_authorization_denied",
                message=str(exc),
            )
            return
        except CatalogNotFoundError as exc:
            await _send_error(
                websocket,
                request_id=request_id,
                code="sql_catalog_not_found",
                message=str(exc),
            )
            return
        wrapped_source = notebook_sql_cell.build_kernel_wrapper(
            source,
            approved_tables=approved,
            result_var=result_var if isinstance(result_var, str) else None,
        )
        sql_cell_metadata[(content_hash, session.session_id)] = {
            "raw_sql": source,
            "approved_tables": list(approved.keys()),
        }
        kernel_source = wrapped_source
    else:
        kernel_source = source
    started_at = datetime.datetime.now(datetime.UTC)
    output_counters.pop((content_hash, session.session_id), None)
    try:
        notebook_outputs_service.clear_cell(
            factory,
            file_path=file_path,
            content_hash=content_hash,
        )
        notebook_outputs_service.upsert_cell_run(
            factory,
            file_path=file_path,
            content_hash=content_hash,
            kernel_session_id=session.session_id,
            status="running",
            finished=False,
        )
        run_source_id = notebook_outputs_service.record_cell_run_start(
            factory,
            file_path=file_path,
            content_hash=content_hash,
            kernel_session_id=session.session_id,
            source=source,
            started_at=started_at,
        )
    except Exception:  # noqa: BLE001
        logger.exception("notebook run-source start failed")
        await _send_error(
            websocket,
            request_id=request_id,
            code="persist_failed",
            message="failed to persist run-source row",
        )
        return
    pending_run_sources[(content_hash, session.session_id)] = run_source_id
    cell_run_started_at[(content_hash, session.session_id)] = started_at
    msg_id = await session.execute(kernel_source, content_hash)
    payload = {
        "id": request_id,
        "result": {"msg_id": msg_id, "kernel_session_id": session.session_id},
    }
    await websocket.send_text(json.dumps(payload))


async def _handle_interrupt(
    websocket: WebSocket,
    *,
    request_id: int | None,
    session: KernelSession,
) -> None:
    """Handle a JSON-RPC ``interrupt`` request — fire SIGINT at kernel."""
    try:
        await session.interrupt()
    except Exception as exc:  # noqa: BLE001 — surface as RPC error
        await _send_error(
            websocket,
            request_id=request_id,
            code="interrupt_failed",
            message=str(exc),
        )
        return
    await websocket.send_text(
        json.dumps({"id": request_id, "result": {"status": "interrupted"}})
    )


async def _handle_restart(
    websocket: WebSocket,
    *,
    request_id: int | None,
    session: KernelSession,
    file_path: str,
    factory: Any,
    pending_run_sources: dict[tuple[str, str], int],
    output_counters: dict[tuple[str, str], int],
) -> None:
    """Handle a JSON-RPC ``restart`` request — bump session id, drop state."""
    old_session_id = session.session_id
    try:
        await session.restart()
    except Exception as exc:  # noqa: BLE001
        await _send_error(
            websocket,
            request_id=request_id,
            code="restart_failed",
            message=str(exc),
        )
        return
    try:
        notebook_outputs_service.clear_session(
            factory,
            file_path=file_path,
            kernel_session_id=old_session_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("notebook_outputs clear_session after restart failed")
    pending_run_sources.clear()
    output_counters.clear()
    await websocket.send_text(
        json.dumps(
            {
                "id": request_id,
                "result": {
                    "status": "restarted",
                    "kernel_session_id": session.session_id,
                },
            }
        )
    )


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
    if not _user_can_use_editor(user):
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
    registry: KernelRegistry | None = getattr(
        websocket.app.state, "kernel_registry", None
    )
    if registry is None:
        await websocket.close(code=4503)
        return
    user_id = int(user.get("id") or 0)
    user_email = str(user.get("email") or "")
    session = await registry.get_or_start(user_id, user_email, relative_path)
    factory = websocket.app.state.session_factory
    await websocket.accept()
    sub = session.subscribe()
    pending_run_sources: dict[tuple[str, str], int] = {}
    output_counters: dict[tuple[str, str], int] = {}
    sql_cell_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    cell_run_started_at: dict[tuple[str, str], datetime.datetime] = {}
    workspace_id = int(getattr(websocket.state, "workspace_id", 0) or 0) or 1
    iopub_task = asyncio.create_task(
        _pump_subscription(
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
        _pump_subscription(
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
                await _send_error(
                    websocket,
                    request_id=None,
                    code="bad_json",
                    message="frame was not valid JSON",
                )
                continue
            if not isinstance(frame, dict):
                await _send_error(
                    websocket,
                    request_id=None,
                    code="bad_frame",
                    message="frame must be a JSON object",
                )
                continue
            request_id_raw = frame.get("id")
            request_id = (
                int(request_id_raw) if isinstance(request_id_raw, int) else None
            )
            method = frame.get("method")
            params = frame.get("params") or {}
            if not isinstance(params, dict):
                await _send_error(
                    websocket,
                    request_id=request_id,
                    code="bad_frame",
                    message="params must be a JSON object",
                )
                continue
            if method == "execute":
                await _handle_execute(
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
                await _handle_interrupt(
                    websocket,
                    request_id=request_id,
                    session=session,
                )
            elif method == "restart":
                await _handle_restart(
                    websocket,
                    request_id=request_id,
                    session=session,
                    file_path=relative_path,
                    factory=factory,
                    pending_run_sources=pending_run_sources,
                    output_counters=output_counters,
                )
            else:
                await _send_error(
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
