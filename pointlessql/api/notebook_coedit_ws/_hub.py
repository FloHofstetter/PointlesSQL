"""Hub lifecycle — create on first subscriber, tear down on last departure."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.api.notebook_coedit_ws._constants import FLUSH_INTERVAL_S
from pointlessql.api.notebook_coedit_ws._seed import build_seed
from pointlessql.api.notebook_coedit_ws._state import (
    HUBS,
    HUBS_LOCK,
    NotebookHub,
)
from pointlessql.models.notebook import NotebookCrdtState
from pointlessql.services.notebook import coedit as coedit_service

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from pointlessql.config import Settings

_LOG = logging.getLogger(__name__)


async def get_or_create_hub(
    notebook_id: str,
    factory: sessionmaker[Any],
    settings: Settings,
) -> NotebookHub:
    """Return the live hub for *notebook_id*, creating it on cold path.

    Cold path loads the persisted blob (or seeds from disk) into a
    fresh in-memory Doc and spawns the periodic flush task.  Warm
    path returns the existing hub unchanged.
    """
    async with HUBS_LOCK:
        hub = HUBS.get(notebook_id)
        if hub is not None:
            return hub
        seed = build_seed(factory, settings, notebook_id=notebook_id)
        with factory() as session:
            doc = coedit_service.get_or_init_ydoc(session, notebook_id=notebook_id, seed_cells=seed)
            session.commit()
        hub = NotebookHub(
            notebook_id=notebook_id,
            doc=doc,
            subscribers=[],
            lock=asyncio.Lock(),
            dirty=False,
            flush_task=None,
        )
        hub.flush_task = asyncio.create_task(
            flush_loop(hub, factory),
            name=f"coedit-flush-{notebook_id[:8]}",
        )
        HUBS[notebook_id] = hub
        return hub


async def release_hub_if_empty(
    notebook_id: str,
    factory: sessionmaker[Any],
) -> None:
    """Tear down the hub when the last subscriber leaves.

    Cancels the periodic flush task, writes a synchronous final
    flush so no edit is lost, and opportunistically compacts the
    blob if it has crossed the size or TTL gate.  Best-effort — any
    DB error is logged but does not propagate.
    """
    async with HUBS_LOCK:
        hub = HUBS.get(notebook_id)
        if hub is None or hub.subscribers:
            return
        flush_task = hub.flush_task
        if flush_task is not None:
            flush_task.cancel()
            try:
                await flush_task
            except asyncio.CancelledError, Exception:  # noqa: BLE001
                pass
        try:
            with factory() as session:
                coedit_service.flush_doc(session, notebook_id=notebook_id, doc=hub.doc)
                row = session.execute(
                    select(NotebookCrdtState).where(NotebookCrdtState.notebook_id == notebook_id)
                ).scalar_one_or_none()
                if row is not None and coedit_service.needs_compaction(row):
                    coedit_service.compact(session, notebook_id=notebook_id)
                session.commit()
        except Exception:  # noqa: BLE001 — teardown must not raise
            _LOG.exception("coedit: final flush failed for %s", notebook_id)
        del HUBS[notebook_id]


async def flush_loop(
    hub: NotebookHub,
    factory: sessionmaker[Any],
) -> None:
    """Periodically snapshot the hub's Doc to the sidecar row.

    Cancelled at hub teardown; the synchronous final flush in
    :func:`release_hub_if_empty` handles the last write.
    """
    try:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            if not hub.dirty:
                continue
            async with hub.lock:
                snapshot = hub.doc.get_update()
                hub.dirty = False
            try:
                with factory() as session:
                    coedit_service._upsert_state(  # pyright: ignore[reportPrivateUsage]
                        session,
                        notebook_id=hub.notebook_id,
                        blob=snapshot,
                    )
                    session.commit()
            except Exception:  # noqa: BLE001 — keep looping on transient DB errors
                _LOG.exception("coedit: periodic flush failed for %s", hub.notebook_id)
                # Re-mark dirty so the next tick retries.
                hub.dirty = True
    except asyncio.CancelledError:
        raise
