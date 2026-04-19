"""Notebook WebSocket endpoints — kernel proxy + LSP proxy.

Sprint 88b split out of ``api/main.py``.  Owns the two
``@app.websocket(...)`` routes that back the native notebook editor:

* ``/ws/notebook/kernel`` (Sprint 59) — bidirectional ZMQ↔WS proxy
  for the per-notebook IPython kernel.  Manual cookie auth (WS
  upgrades bypass the HTTP middleware), shared-kernel routing
  through ``services.kernel_session.KernelRegistry``, persistence
  of every iopub message into ``notebook_outputs`` so the editor
  can replay the last run on reload.
* ``/ws/notebook/lsp`` (Sprint 61) — pyright-langserver proxy.
  One subprocess per WS connection (per-tab isolation), pure
  framing proxy that adds + strips the ``Content-Length`` LSP
  header.

Auth model is unchanged from the pre-split shape: WS upgrades pull
the ``pql_session`` cookie manually and decode the JWT through
``auth_service.get_current_user``.  Both routes 4401 on missing /
invalid cookie and 4400 on a notebook path that fails the same
traversal guard the HTTP save endpoint uses.

Internal ``__pql_``-prefixed cell IDs are reserved for editor-
driven introspects (Variable Explorer namespace scan, future
autocomplete helpers); their kernel messages are routed back to
the client but never persisted into ``notebook_outputs``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from pointlessql.exceptions import ValidationError
from pointlessql.services import auth as auth_service
from pointlessql.services import kernel_session as kernel_session_service
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import notebook_outputs as notebook_outputs_service
from pointlessql.services import pyright_bridge as pyright_bridge_service
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks-ws"])


async def resolve_sql_approved_tables(
    websocket: WebSocket,
    settings: Settings,
    user: UserInfo,
    query: str,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Parse a SQL string and return ``(approved_tables, error_or_none)``.

    Sprint 71 — shared shape with ``POST /api/sql/execute``: parse via
    :func:`prepare_sql`, look up every referenced 3-part name in
    soyuz-catalog, and run :func:`check_privilege` for ``SELECT`` so
    the kernel never sees a query the caller does not have rights to
    run.  Returns the ``approved_tables`` map on success, or an
    ``error`` content dict shaped like an iopub ``error`` message
    (``ename`` / ``evalue`` / ``traceback``) on any failure so the WS
    handler can ship a synthetic kernel_msg straight to the cell's
    output zone.

    Args:
        websocket: WebSocket whose ``app.state`` holds settings.
        settings: Application settings (needed for ``sql.enabled``).
        user: Authenticated user from the JWT cookie.
        query: SQL source as typed in the cell.

    Returns:
        ``(approved_tables, None)`` on success — the dict maps every
        ``catalog.schema.table`` reference to its Delta storage
        location.  ``({}, error_dict)`` on failure (parse error,
        unknown table, missing storage location, denied privilege).
    """
    from pointlessql.exceptions import (
        AuthorizationError,
        CatalogNotFoundError,
        SQLExecutionError,
    )
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    del websocket  # accepted for symmetry with HTTP-route shape; not used here

    try:
        prepared = prepare_sql(query)
    except SQLParseError as exc:
        return {}, {
            "ename": "SQLParseError",
            "evalue": str(exc),
            "traceback": [],
        }

    client = UnityCatalogClient.for_principal(settings, user["email"])
    email = user["email"]
    is_admin = bool(user.get("is_admin", False))
    approved: dict[str, str] = {}
    try:
        for full_name in prepared.refs:
            parts = full_name.split(".")
            if len(parts) != 3:
                return {}, {
                    "ename": "SQLExecutionError",
                    "evalue": f"Internal error: expected 3-part name, got {full_name!r}.",
                    "traceback": [],
                }
            table_info = await client.get_table(parts[0], parts[1], parts[2])
            if not table_info:
                return {}, {
                    "ename": "CatalogNotFoundError",
                    "evalue": f"Table not found: {full_name!r}",
                    "traceback": [],
                }
            storage_location = table_info.get("storage_location")
            if not isinstance(storage_location, str) or not storage_location:
                return {}, {
                    "ename": "CatalogNotFoundError",
                    "evalue": (
                        f"Table {full_name!r} has no storage_location on soyuz-catalog."
                    ),
                    "traceback": [],
                }
            await check_privilege(client, email, is_admin, "table", full_name, SELECT)
            approved[full_name] = storage_location
    except AuthorizationError as exc:
        return {}, {
            "ename": "AuthorizationError",
            "evalue": str(exc),
            "traceback": [],
        }
    except (CatalogNotFoundError, SQLExecutionError) as exc:
        return {}, {
            "ename": type(exc).__name__,
            "evalue": str(exc),
            "traceback": [],
        }
    finally:
        await client.aclose()

    return approved, None


@router.websocket("/ws/notebook/kernel")
async def ws_notebook_kernel(websocket: WebSocket, path: str) -> None:
    """Bidirectional ZMQ↔WS proxy for the native-editor kernel.

    Sprint 59 endpoint. WebSocket upgrades bypass the HTTP auth
    middleware, so we pull the ``pql_session`` cookie manually and
    decode the JWT via :func:`auth_service.get_current_user`. A
    client frame is a JSON object with ``type`` in
    ``{"execute", "interrupt", "restart"}``; the server responds
    with ``type`` in ``{"hello", "ack", "restarted", "kernel_msg",
    "error"}``.

    One WS connection maps to one subscriber on the shared kernel;
    a second tab for the same ``(user, notebook_path)`` pair gets a
    second subscription on the same subprocess — ADR-0001 "kernel
    per notebook path" decision.

    Args:
        websocket: Incoming FastAPI WebSocket.
        path: Relative notebook path (query param) — validated with
            the same traversal guard the HTTP save endpoint uses.
    """
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if not token:
        await websocket.close(code=4401)
        return

    factory = websocket.app.state.session_factory
    settings: Settings = websocket.app.state.settings
    user = auth_service.get_current_user(
        factory,
        token,
        settings.auth.secret_key,
        previous_key=settings.auth.secret_key_previous,
    )
    if user is None:
        await websocket.close(code=4401)
        return

    try:
        notebook_doc_service.resolve_py_notebook_path(
            settings.jupyter.notebooks_dir.resolve(),
            path,
            must_exist=False,
        )
    except ValidationError:
        await websocket.close(code=4400)
        return

    await websocket.accept()

    registry: kernel_session_service.KernelRegistry = (
        websocket.app.state.kernel_registry
    )
    try:
        session = await registry.get_or_start(user["id"], user["email"], path)
    except Exception as exc:  # noqa: BLE001 — kernel start can fail for many reasons
        logger.exception("kernel start failed for %s notebook=%s", user["email"], path)
        await websocket.send_json(
            {"type": "error", "message": f"kernel start failed: {exc}"},
        )
        await websocket.close(code=1011)
        return

    subscription = session.subscribe()
    await websocket.send_json(
        {
            "type": "hello",
            "kernel_session_id": session.session_id,
            "notebook_path": path,
        },
    )

    # Sprint 60: per-(cell_id, kernel_session_id) output counter.
    # A new `execute` on a cell wipes the previous outputs (both in
    # memory and in the DB via ``clear_cell``) and resets its
    # counter to 0, so persisted rows always stay contiguous.
    output_counters: dict[tuple[str, str], int] = {}
    # Sprint 73: pending run-source ids keyed by ``(cell_id,
    # kernel_session_id)``.  ``record_cell_run_start`` returns the
    # autoincrement id on execute; the matching execute_reply pops
    # the id and calls ``record_cell_run_finish`` to stamp status +
    # finish + execution_count.  Cleared on WS disconnect / restart
    # so a dropped reply never leaks rows.
    pending_run_sources: dict[tuple[str, str], int] = {}

    # Sprint 62: ``__pql_``-prefixed cell IDs are reserved for the
    # editor's internal introspects (Variable Explorer namespace
    # scan, future autocomplete helpers).  Skipping persistence on
    # these keeps the ``notebook_outputs`` table free of silent-
    # execute rows that never surface in the UI.
    def _is_internal_cell(cell_id: str | None) -> bool:
        return bool(cell_id) and cell_id.startswith("__pql_")

    async def _persist_kernel_msg(msg: kernel_session_service.KernelMessage) -> None:
        if not msg.cell_id or _is_internal_cell(msg.cell_id):
            return
        if not notebook_outputs_service.is_persistable(msg.msg_type):
            return
        key = (msg.cell_id, session.session_id)
        idx = output_counters.get(key, 0)
        output_counters[key] = idx + 1
        await asyncio.to_thread(
            notebook_outputs_service.append_output,
            factory,
            file_path=path,
            cell_id=msg.cell_id,
            kernel_session_id=session.session_id,
            output_index=idx,
            msg_type=msg.msg_type,
            content=msg.content,
            metadata=msg.metadata or None,
        )

    async def _handle_shell_lifecycle(
        msg: kernel_session_service.KernelMessage,
    ) -> None:
        if msg.msg_type != "execute_reply" or not msg.cell_id:
            return
        if _is_internal_cell(msg.cell_id):
            return
        raw_status = msg.content.get("status", "ok")
        status: str = raw_status if isinstance(raw_status, str) else "ok"
        execution_count = msg.content.get("execution_count")
        ec_int = execution_count if isinstance(execution_count, int) else None
        await asyncio.to_thread(
            notebook_outputs_service.upsert_cell_run,
            factory,
            file_path=path,
            cell_id=msg.cell_id,
            kernel_session_id=session.session_id,
            status=status,
            execution_count=ec_int,
            finished=True,
        )
        # Sprint 73: stamp the per-execute history row this reply
        # belongs to.  Lookup is by (cell_id, kernel_session_id) —
        # the kernel serialises execute_requests so the queued
        # reply matches the most recent start in flight for that
        # key.  Pop on success so a bug in the kernel that emits
        # two replies for one request does not double-stamp.
        source_id = pending_run_sources.pop(
            (msg.cell_id, session.session_id), None,
        )
        if source_id is not None:
            await asyncio.to_thread(
                notebook_outputs_service.record_cell_run_finish,
                factory,
                source_id=source_id,
                status=status,
                execution_count=ec_int,
                finished_at=datetime.now(UTC),
            )

    async def _forward(channel: str) -> None:
        queue = subscription.iopub if channel == "iopub" else subscription.shell
        try:
            async for msg in kernel_session_service.drain(queue):
                if channel == "iopub":
                    await _persist_kernel_msg(msg)
                else:
                    await _handle_shell_lifecycle(msg)
                payload = {
                    "type": "kernel_msg",
                    "channel": msg.channel,
                    "msg_type": msg.msg_type,
                    "cell_id": msg.cell_id,
                    "parent_msg_id": msg.parent_msg_id,
                    "content": jsonable_encoder(msg.content),
                    "metadata": jsonable_encoder(msg.metadata),
                }
                await websocket.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            return

    forward_tasks = [
        asyncio.create_task(_forward("iopub"), name="ws-kernel-iopub"),
        asyncio.create_task(_forward("shell"), name="ws-kernel-shell"),
    ]

    async def _wipe_cell_for_new_execute(cell_id: str, source: str) -> None:
        """Reset persistence + counter state before a fresh execute.

        Sprint 71 factored out of the ``execute`` branch so the new
        ``execute_sql`` branch can share the same prelude (clear
        previous outputs, drop the per-cell index, mark the run as
        ``running``).  Sprint 73 extends it to also insert a per-
        execute history row via ``record_cell_run_start`` and stash
        the returned id in ``pending_run_sources`` so the matching
        execute_reply can stamp the finish.  Internal
        ``__pql_``-prefixed cells stay unpersisted, so this is a
        no-op for them.

        Args:
            cell_id: Cell UUID.
            source: Source the kernel will execute (raw Python for
                ``execute``, wrapped ``__pql_sql_run(...)`` snippet
                for ``execute_sql``).  Stored verbatim in the
                history row.
        """
        if _is_internal_cell(cell_id):
            return
        await asyncio.to_thread(
            notebook_outputs_service.clear_cell,
            factory, file_path=path, cell_id=cell_id,
        )
        output_counters.pop((cell_id, session.session_id), None)
        # Drop any orphan from a dropped reply on the prior run for
        # this key so the new start doesn't double-stamp the wrong id
        # when the next reply arrives.
        pending_run_sources.pop((cell_id, session.session_id), None)
        await asyncio.to_thread(
            notebook_outputs_service.upsert_cell_run,
            factory,
            file_path=path,
            cell_id=cell_id,
            kernel_session_id=session.session_id,
            status="running",
        )
        source_id = await asyncio.to_thread(
            notebook_outputs_service.record_cell_run_start,
            factory,
            file_path=path,
            cell_id=cell_id,
            kernel_session_id=session.session_id,
            source=source,
            started_at=datetime.now(UTC),
        )
        pending_run_sources[(cell_id, session.session_id)] = source_id

    try:
        while True:
            frame = await websocket.receive_json()
            ftype = frame.get("type")
            if ftype == "execute":
                code = frame.get("code", "")
                cell_id = frame.get("cell_id", "")
                if not isinstance(code, str) or not isinstance(cell_id, str):
                    await websocket.send_json(
                        {"type": "error", "message": "execute needs string code + cell_id"},
                    )
                    continue
                await _wipe_cell_for_new_execute(cell_id, code)
                msg_id = await session.execute(code, cell_id)
                await websocket.send_json(
                    {"type": "ack", "msg_id": msg_id, "cell_id": cell_id},
                )
            elif ftype == "execute_sql":
                # Sprint 71: SQL cell.  Parse + privilege-check the
                # query route-side (mirrors ``/api/sql/execute``), then
                # send a wrapped ``__pql_sql_run(...)`` snippet to the
                # kernel for execution.  The kernel-side helper builds
                # a pandas DataFrame from the result, optionally binds
                # it under ``result_var`` so Variable Explorer surfaces
                # it, and ``display(df)`` so the existing rich-mime
                # path renders the table inline.
                source = frame.get("source", "")
                cell_id = frame.get("cell_id", "")
                result_var = frame.get("result_var")
                if (
                    not isinstance(source, str)
                    or not isinstance(cell_id, str)
                    or (result_var is not None and not isinstance(result_var, str))
                ):
                    await websocket.send_json({
                        "type": "error",
                        "message": (
                            "execute_sql needs string source + cell_id "
                            "(and optional string result_var)"
                        ),
                    })
                    continue
                if not settings.sql.enabled:
                    await websocket.send_json({
                        "type": "kernel_msg",
                        "channel": "iopub",
                        "msg_type": "error",
                        "cell_id": cell_id,
                        "parent_msg_id": None,
                        "content": {
                            "ename": "SQLDisabled",
                            "evalue": "The SQL editor is disabled on this deployment.",
                            "traceback": [],
                        },
                        "metadata": {},
                    })
                    continue
                approved, err = await resolve_sql_approved_tables(
                    websocket, settings, user, source,
                )
                if err is not None:
                    await websocket.send_json({
                        "type": "kernel_msg",
                        "channel": "iopub",
                        "msg_type": "error",
                        "cell_id": cell_id,
                        "parent_msg_id": None,
                        "content": err,
                        "metadata": {},
                    })
                    continue
                wrapped = (
                    "__pql_sql_run("
                    f"{json.dumps(source)}, "
                    f"approved_tables={json.dumps(approved)}, "
                    f"result_var={json.dumps(result_var) if result_var else 'None'}, "
                    f"max_rows={int(settings.sql.max_rows)}"
                    ")"
                )
                await _wipe_cell_for_new_execute(cell_id, wrapped)
                msg_id = await session.execute(wrapped, cell_id)
                await websocket.send_json(
                    {"type": "ack", "msg_id": msg_id, "cell_id": cell_id},
                )
            elif ftype == "interrupt":
                await session.interrupt()
                await websocket.send_json({"type": "interrupted"})
            elif ftype == "restart":
                # Purge the outgoing session's rows *before* the
                # kernel starts handing out a new session_id.
                await asyncio.to_thread(
                    notebook_outputs_service.clear_session,
                    factory,
                    file_path=path,
                    kernel_session_id=session.session_id,
                )
                output_counters.clear()
                pending_run_sources.clear()
                await session.restart()
                await websocket.send_json(
                    {
                        "type": "restarted",
                        "kernel_session_id": session.session_id,
                    },
                )
            elif ftype == "clear_cell":
                cell_id = frame.get("cell_id", "")
                if isinstance(cell_id, str) and cell_id:
                    await asyncio.to_thread(
                        notebook_outputs_service.clear_cell,
                        factory, file_path=path, cell_id=cell_id,
                    )
                    output_counters.pop((cell_id, session.session_id), None)
                await websocket.send_json({"type": "cell_cleared", "cell_id": cell_id})
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"unknown frame type {ftype!r}"},
                )
    except WebSocketDisconnect:
        pass
    finally:
        for task in forward_tasks:
            task.cancel()
        for task in forward_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        session.unsubscribe(subscription)


@router.websocket("/ws/notebook/lsp")
async def ws_notebook_lsp(websocket: WebSocket, path: str) -> None:
    """Bidirectional LSP JSON-RPC proxy for the notebook editor.

    Sprint 61 endpoint.  Mirrors the Sprint-59 kernel WS: manual
    cookie-based auth (WS upgrades bypass HTTP middleware), same
    traversal guard for the notebook path.  One pyright-langserver
    subprocess is spawned per WS connection and torn down on
    disconnect — per-tab isolation keeps the routing trivial.

    The WS frames carry raw LSP JSON-RPC messages (request /
    response / notification) verbatim.  The server is a pure
    framing proxy: it adds the ``Content-Length`` header on the
    way in, strips it on the way out.  Client code can therefore
    use any off-the-shelf LSP client or (in our case) a hand-
    rolled minimal one on top of Monaco's provider APIs.

    Args:
        websocket: Incoming FastAPI WebSocket.
        path: Relative notebook path (query param). Validated with
            the same traversal guard as the save endpoint.
    """
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if not token:
        await websocket.close(code=4401)
        return

    factory = websocket.app.state.session_factory
    settings: Settings = websocket.app.state.settings
    user = auth_service.get_current_user(
        factory,
        token,
        settings.auth.secret_key,
        previous_key=settings.auth.secret_key_previous,
    )
    if user is None:
        await websocket.close(code=4401)
        return

    try:
        notebook_doc_service.resolve_py_notebook_path(
            settings.jupyter.notebooks_dir.resolve(),
            path,
            must_exist=False,
        )
    except ValidationError:
        await websocket.close(code=4400)
        return

    if pyright_bridge_service.find_pyright_langserver() is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    async def _forward_from_pyright(message: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(message))
        except WebSocketDisconnect:
            return

    session = pyright_bridge_service.PyrightSession(_forward_from_pyright)
    try:
        await session.start()
    except Exception as exc:  # noqa: BLE001 — langserver spawn can fail in several ways
        logger.exception("pyright-langserver start failed for %s", user["email"])
        await websocket.send_json({
            "type": "error",
            "message": f"pyright start failed: {exc}",
        })
        await websocket.close(code=1011)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            await session.send(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await session.shutdown()
