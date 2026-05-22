"""JSON-RPC method handlers — execute / interrupt / restart."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import WebSocket

from pointlessql.api.notebook_kernel_ws._protocol import send_error
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogNotFoundError,
)
from pointlessql.pql import SQLParseError
from pointlessql.services.notebook import _sql_cell as notebook_sql_cell
from pointlessql.services.notebook import magic_commands as notebook_magic_commands
from pointlessql.services.notebook import outputs as notebook_outputs_service
from pointlessql.services.notebook.kernel_session import KernelSession
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def handle_execute(
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
        await send_error(
            websocket,
            request_id=request_id,
            code="bad_params",
            message="execute params.content_hash must be a non-empty string",
        )
        return
    if not isinstance(source, str):
        await send_error(
            websocket,
            request_id=request_id,
            code="bad_params",
            message="execute params.source must be a string",
        )
        return
    cell_type = params.get("cell_type") or "code"
    result_var = params.get("result_var")
    # ``silent`` here means "this is an internal probe — skip
    # IPython history + skip the notebook_cell_run persistence."
    # The Variable Inspector polls hit this path; without it,
    # IPython's ``_ih`` / ``_oh`` grew indefinitely and the
    # notebook_cell_runs table accumulated rows for every probe
    # (caught Phase 105 replay).
    silent = bool(params.get("silent"))
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
            await send_error(
                websocket,
                request_id=request_id,
                code="sql_parse_error",
                message=str(exc),
            )
            return
        except AuthorizationError as exc:
            await send_error(
                websocket,
                request_id=request_id,
                code="sql_authorization_denied",
                message=str(exc),
            )
            return
        except CatalogNotFoundError as exc:
            await send_error(
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
    elif cell_type == "code" and notebook_magic_commands.has_magics(source):
        # Phase 98.A — rewrite %sql / %md / %fs ls / %timeit lines.
        # SQL fragments need server-side approval resolution before
        # the wrapper call is spliced back into the placeholder.
        pre = notebook_magic_commands.preprocess(source)
        wrappers: list[str] = []
        for block in pre.sql_blocks:
            try:
                uc_client = websocket.app.state.uc_client
                approved = await notebook_sql_cell.resolve_approved_tables(
                    block.sql,
                    uc_client=uc_client,
                    actor_email=str(user.get("email") or ""),
                    is_admin=bool(user.get("is_admin")),
                )
            except SQLParseError as exc:
                await send_error(
                    websocket,
                    request_id=request_id,
                    code="sql_parse_error",
                    message=f"%sql line {block.index}: {exc}",
                )
                return
            except AuthorizationError as exc:
                await send_error(
                    websocket,
                    request_id=request_id,
                    code="sql_authorization_denied",
                    message=f"%sql line {block.index}: {exc}",
                )
                return
            except CatalogNotFoundError as exc:
                await send_error(
                    websocket,
                    request_id=request_id,
                    code="sql_catalog_not_found",
                    message=f"%sql line {block.index}: {exc}",
                )
                return
            wrappers.append(
                notebook_sql_cell.build_kernel_wrapper(
                    block.sql,
                    approved_tables=approved,
                    result_var=block.result_var,
                ).strip()
            )
        kernel_source = notebook_magic_commands.apply_sql_resolutions(
            pre.source, wrappers=wrappers
        )
    else:
        kernel_source = source
    started_at = datetime.datetime.now(datetime.UTC)
    output_counters.pop((content_hash, session.session_id), None)
    if not silent:
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
            await send_error(
                websocket,
                request_id=request_id,
                code="persist_failed",
                message="failed to persist run-source row",
            )
            return
        pending_run_sources[(content_hash, session.session_id)] = run_source_id
        cell_run_started_at[(content_hash, session.session_id)] = started_at
    msg_id = await session.execute(kernel_source, content_hash, silent=silent)
    payload = {
        "id": request_id,
        "result": {"msg_id": msg_id, "kernel_session_id": session.session_id},
    }
    await websocket.send_text(json.dumps(payload))


async def handle_interrupt(
    websocket: WebSocket,
    *,
    request_id: int | None,
    session: KernelSession,
) -> None:
    """Handle a JSON-RPC ``interrupt`` request — fire SIGINT at kernel."""
    try:
        await session.interrupt()
    except Exception as exc:  # noqa: BLE001 — surface as RPC error
        # bare-broad-ok: kernel interrupt errors are surfaced to the
        # browser via the structured JSON-RPC error envelope; that IS
        # the diagnostic, server-side log would be noise.
        await send_error(
            websocket,
            request_id=request_id,
            code="interrupt_failed",
            message=str(exc),
        )
        return
    await websocket.send_text(
        json.dumps({"id": request_id, "result": {"status": "interrupted"}})
    )


async def handle_restart(
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
        # bare-broad-ok: kernel restart errors are surfaced to the
        # browser via the structured JSON-RPC error envelope.
        await send_error(
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
