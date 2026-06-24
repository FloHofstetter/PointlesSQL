"""Notebook replay re-execution worker.

Picks ``pending`` :class:`~pointlessql.models.notebook.NotebookReplay`
rows, marks them ``running``, spins up an isolated Python kernel via
``jupyter_client.AsyncKernelManager`` (same dependency the live
``KernelSession`` uses), re-runs every cell from the pinned
revision, and records the per-cell outputs back onto the replay row.

The worker is deliberately self-contained:

* one row per tick (no concurrency); replays are bursty and a serial
  worker keeps the design auditable and prevents two replays from
  fighting over a branched schema in :func:`PQL._branch_remap`;
* a fresh kernel per replay so previously executed cells in one
  replay can't leak state into the next;
* the optional ``branch_name`` column flows into the kernel via
  ``POINTLESSQL_BRANCH`` so writes route through the bound branch
 ;
* errors mark the row ``error`` and store ``[{ "msg_type": "error",
  ... }]`` as outputs so the diff surface still has something to
  show ("first error in cell N").

Lifespan integration mirrors :class:`pointlessql.services.scheduler.loop.Scheduler`
— a single coroutine kicked off by the FastAPI lifespan, awaited
during shutdown.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from pointlessql.models.notebook import NotebookReplay
from pointlessql.services.notebook import replay as replay_service
from pointlessql.services.notebook import revisions as revisions_service
from pointlessql.services.notebook._replay_logic import (
    build_error_frame,
    build_output_frame,
    frame_has_error,
    is_idle_status,
    is_output_message,
    message_matches_parent,
    prepare_kernel_env,
    serialise_content,
    should_execute_cell,
)

logger = logging.getLogger(__name__)

#: Default tick — replays are interactive (a user kicked one off
#: from the panel and is staring at the row), so faster than the
#: scheduler's job-tick is appropriate.
DEFAULT_TICK_SECONDS = 5
#: Per-cell execute timeout; matches the papermill default so a
#: hung cell can't pin the worker indefinitely.
DEFAULT_CELL_TIMEOUT_SECONDS = 300


async def _execute_one_replay(
    *,
    session_factory: Any,
    replay_row: NotebookReplay,
    notebooks_dir: Path,
) -> None:
    """Re-execute every cell of the pinned revision; record outputs.

    Args:
        session_factory: A SQLAlchemy ``sessionmaker``.
        replay_row: The :class:`NotebookReplay` to process (already
            marked ``running`` by the caller).
        notebooks_dir: Kernel working directory.

    Notes:
        Uses :mod:`jupyter_client` so the kernel inherits the
        same env-bridge contract as the editor's live kernel.
        Failures mark the row ``error`` with a single ``error``
        frame so the diff surface still has something to show.
    """
    from jupyter_client import AsyncKernelManager  # pyright: ignore[reportPrivateImportUsage]

    # Load the base revision's cells.
    with session_factory() as session:
        rev = revisions_service.get_revision(session, revision_uuid=replay_row.base_revision_uuid)
        if rev is None:
            replay_service.record_finished(
                session,
                replay_uuid=replay_row.replay_uuid,
                status=replay_service.REPLAY_STATUS_ERROR,
                outputs=[
                    build_error_frame(
                        content_hash="__no_revision__",
                        kernel_session_id="worker",
                        ename="ReplayError",
                        evalue="base revision missing",
                        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
                    )
                ],
            )
            session.commit()
        cells: list[dict[str, Any]] = rev["cells"] if rev else []
        branch_name = replay_row.branch_name

    # Spin up an isolated kernel.  ``cwd`` is a fresh tempdir so the
    # replay doesn't pollute the notebooks_dir; ``POINTLESSQL_BRANCH``
    # routes writes through the bound branch when set.
    env = prepare_kernel_env(os.environ, branch_name)
    cwd = Path(tempfile.mkdtemp(prefix="replay-")) if not notebooks_dir.exists() else notebooks_dir
    km: AsyncKernelManager | None = None
    kc = None
    session_id = uuid.uuid4().hex[:12]
    collected: list[dict[str, Any]] = []
    final_status = replay_service.REPLAY_STATUS_OK
    try:
        km = AsyncKernelManager()
        await km.start_kernel(env=env, cwd=str(cwd))  # pyright: ignore[reportOptionalMemberAccess]
        kc = km.client()  # pyright: ignore[reportOptionalMemberAccess]
        kc.start_channels()
        await kc.wait_for_ready(timeout=30)
        # Skip markdown cells; only code + sql execute.  SQL cells
        # carry plain Python source via the magic-command pre-processor
        # in interactive use; replays just run the raw source as-is.
        for index, cell in enumerate(cells):
            cell_type = cell.get("cell_type") or "code"
            content_hash = cell.get("content_hash") or ""
            source = cell.get("source") or ""
            if not should_execute_cell(cell_type, source):
                continue
            try:
                frames = await _execute_one_cell(
                    kc=kc,
                    source=source,
                    content_hash=content_hash,
                    session_id=session_id,
                    timeout=DEFAULT_CELL_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                frames = [
                    build_error_frame(
                        content_hash=content_hash,
                        kernel_session_id=session_id,
                        ename="TimeoutError",
                        evalue=f"cell {index + 1} exceeded {DEFAULT_CELL_TIMEOUT_SECONDS}s",
                        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
                    )
                ]
                final_status = replay_service.REPLAY_STATUS_ERROR
            collected.extend(frames)
            # Short-circuit on the first error so the user sees
            # the failure cause without waiting for downstream
            # cells to also fail.
            if frame_has_error(frames):
                final_status = replay_service.REPLAY_STATUS_ERROR
                break
    except Exception as exc:  # noqa: BLE001
        logger.exception("replay worker failure")
        collected.append(
            build_error_frame(
                content_hash="__worker__",
                kernel_session_id=session_id,
                ename=exc.__class__.__name__,
                evalue=str(exc),
                created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
        )
        final_status = replay_service.REPLAY_STATUS_ERROR
    finally:
        try:
            if kc is not None:
                kc.stop_channels()
        except Exception:  # noqa: BLE001
            logger.exception("replay kernel client stop failed")
        try:
            if km is not None:
                await km.shutdown_kernel(now=True)
        except Exception:  # noqa: BLE001
            logger.exception("replay kernel shutdown failed")

    with session_factory() as session:
        replay_service.record_finished(
            session,
            replay_uuid=replay_row.replay_uuid,
            status=final_status,
            outputs=collected,
        )
        session.commit()
    logger.info(
        "replay %s finished status=%s frames=%d",
        replay_row.replay_uuid,
        final_status,
        len(collected),
    )


async def _execute_one_cell(
    *,
    kc: Any,
    source: str,
    content_hash: str,
    session_id: str,
    timeout: int,
) -> list[dict[str, Any]]:
    """Run *source* on the kernel, capture stream / display / error frames.

    Args:
        kc: An open ``AsyncKernelClient``.
        source: Cell source string.
        content_hash: Cell identity column the load-shape carries.
        session_id: Worker session id (used as ``kernel_session_id``).
        timeout: Per-cell execute timeout in seconds.

    Returns:
        List of output frames in the load-shape used by
        :func:`pointlessql.services.notebook.outputs.load_outputs_for_path`.

    Raises:
        TimeoutError: When the kernel does not reply within *timeout*.
    """
    msg_id: str = kc.execute(source, silent=False, store_history=False)
    frames: list[dict[str, Any]] = []
    deadline = asyncio.get_running_loop().time() + timeout
    output_index = 0
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("cell timed out")
        try:
            msg = await asyncio.wait_for(kc.get_iopub_msg(), timeout=remaining)
        except TimeoutError as e:
            raise TimeoutError("cell timed out") from e
        if not message_matches_parent(msg, msg_id):
            continue
        msg_type = msg.get("msg_type") or ""
        content = msg.get("content") or {}
        if is_idle_status(msg_type, content):
            break
        if is_output_message(msg_type):
            frames.append(
                build_output_frame(
                    content_hash=content_hash,
                    kernel_session_id=session_id,
                    output_index=output_index,
                    msg_type=msg_type,
                    content=serialise_content(msg_type, content),
                    metadata=content.get("metadata"),
                    created_at=datetime.datetime.now(datetime.UTC).isoformat(),
                )
            )
            output_index += 1
    return frames


async def run_pending_replays(
    *,
    session_factory: Any,
    notebooks_dir: Path,
) -> int:
    """Tick: pick at most one pending replay, run it, return processed count.

    Args:
        session_factory: ``sessionmaker``.
        notebooks_dir: Kernel cwd root.

    Returns:
        ``1`` when a row was processed; ``0`` when none was pending.
    """
    with session_factory() as session:
        row = session.execute(
            select(NotebookReplay)
            .where(NotebookReplay.status == replay_service.REPLAY_STATUS_PENDING)
            .order_by(NotebookReplay.started_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return 0
        replay_service.mark_running(session, replay_uuid=row.replay_uuid)
        session.commit()
        # Re-load so we hand the detached row a fresh, fully-attached
        # snapshot — the executor opens its own sessions.
        row = session.execute(
            select(NotebookReplay).where(NotebookReplay.replay_uuid == row.replay_uuid)
        ).scalar_one()
        session.expunge(row)
    await _execute_one_replay(
        session_factory=session_factory,
        replay_row=row,
        notebooks_dir=notebooks_dir,
    )
    return 1


class ReplayWorker:
    """Long-running loop that drains the pending-replay queue.

    Mirrors :class:`pointlessql.services.scheduler.loop.Scheduler` —
    one coroutine, started by the FastAPI lifespan, stopped on
    shutdown.  Failures inside :func:`run_pending_replays` are
    logged and the loop continues — a single bad row should not
    take the worker down.
    """

    def __init__(
        self,
        *,
        session_factory: Any,
        notebooks_dir: Path,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._notebooks_dir = notebooks_dir
        self._tick_seconds = max(1, tick_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Schedule the loop on the running event loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="pointlessql-replay-worker")
        logger.info("replay-worker: started (tick=%ds)", self._tick_seconds)

    async def stop(self) -> None:
        """Signal + await loop termination."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=self._tick_seconds * 2)
        except TimeoutError:
            self._task.cancel()
        self._task = None
        logger.info("replay-worker: stopped")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await run_pending_replays(
                    session_factory=self._session_factory,
                    notebooks_dir=self._notebooks_dir,
                )
                if processed == 0:
                    # No work — wait the full tick before re-polling.
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._tick_seconds,
                        )
                    except TimeoutError:
                        pass
            except Exception:  # noqa: BLE001
                logger.exception("replay-worker tick failed; continuing")
                await asyncio.sleep(self._tick_seconds)


__all__ = [
    "DEFAULT_CELL_TIMEOUT_SECONDS",
    "DEFAULT_TICK_SECONDS",
    "ReplayWorker",
    "run_pending_replays",
]
