"""ZMQ-channel pumps: forward kernel iopub/shell frames to the browser.

The pump is the persistence side-effect.  Every ``stream`` /
``execute_result`` / ``display_data`` / ``error`` iopub frame lands
in ``notebook_outputs`` so a page reload can replay the cell view
without re-executing.  ``execute_reply`` on shell finalises the
matching ``notebook_cell_run_sources`` row and (for SQL cells)
writes the audit ``query_history`` entry.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from pointlessql.api.notebook_kernel_ws._protocol import RESERVED_BOOTSTRAP_HASH
from pointlessql.services import query_history as query_history_service
from pointlessql.services.notebook import outputs as notebook_outputs_service
from pointlessql.services.notebook.kernel_session import (
    KernelMessage,
    KernelSession,
    Subscription,
    drain,
)
from pointlessql.types import UserInfo
from pointlessql.types._enums import QueryStatus

logger = logging.getLogger(__name__)


async def pump_subscription(
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

    Mirrors the persistence side-effect the deleted legacy handler
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
            await handle_kernel_message(
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


async def handle_kernel_message(
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
    if msg.content_hash == RESERVED_BOOTSTRAP_HASH:
        # Skip bootstrap echoes — the helper definition is internal.
        return

    # Jupyter Debug Protocol events.  DAP events (``stopped`` /
    # ``continued`` / ``thread`` / …) arrive on iopub as ``debug_event``
    # frames parented to a control-channel ``debug_request`` — they
    # never carry a content_hash, so they must be forwarded before the
    # per-cell routing below would drop or mis-route them.  The
    # browser-side debugger mixin reacts (e.g. fetching the stack
    # trace on ``stopped``); nothing is persisted because debug state
    # is transient to the live kernel.
    if channel == "iopub" and msg.msg_type == "debug_event":
        await websocket.send_text(
            json.dumps({"notify": "debug_event", "params": {"content": msg.content}})
        )
        return

    # Variable Inspector custom-MIME interception.
    # ``__pql_inspect__`` / ``__pql_inspect_detail__`` emit
    # ``display_data`` frames carrying our private MIMEs. Route them as
    # a dedicated ``variable_snapshot`` / ``variable_detail`` notify
    # instead of persisting them in ``notebook_outputs``: variable
    # snapshots are transient (re-emitted after every cell run) and
    # would otherwise clutter cell-output replay.
    if channel == "iopub" and msg.msg_type in {"display_data", "execute_result"}:
        data_bundle: Any = msg.content.get("data") if isinstance(msg.content, dict) else None
        if isinstance(data_bundle, dict):
            vars_payload = data_bundle.get("application/x-pql-vars+json")
            detail_payload = data_bundle.get("application/x-pql-vardetail+json")
            if vars_payload is not None or detail_payload is not None:
                notify_payload: dict[str, Any] = {
                    "notify": (
                        "variable_detail" if detail_payload is not None else "variable_snapshot"
                    ),
                    "params": {
                        "kernel_session_id": session.session_id,
                        "payload": detail_payload if detail_payload is not None else vars_payload,
                    },
                }
                await websocket.send_text(json.dumps(notify_payload))
                return

    if (
        channel == "iopub"
        and msg.content_hash is not None
        and not msg.content_hash.startswith("__pql_")
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
        and not msg.content_hash.startswith("__pql_")
    ):
        status = str(msg.content.get("status", "ok"))
        execution_count_raw = msg.content.get("execution_count")
        execution_count = int(execution_count_raw) if isinstance(execution_count_raw, int) else None
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
        run_source_id = pending_run_sources.pop((msg.content_hash, session.session_id), None)
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
        sql_meta = sql_cell_metadata.pop((msg.content_hash, session.session_id), None)
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
                    status=QueryStatus.SUCCEEDED if status == "ok" else QueryStatus.FAILED,
                    row_count=None,
                    duration_ms=duration_ms,
                    referenced_tables=list(sql_meta.get("approved_tables") or []),
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
