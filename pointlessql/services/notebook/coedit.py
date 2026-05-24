"""Sidecar Y.Doc persistence for Phase-105 real-time co-edit.

Each notebook gets one persistent :class:`pycrdt.Doc` mirrored into
the ``notebook_crdt_state`` table.  This module owns the load / patch
/ flush cycle plus initial seeding from the on-disk ``.py``.  The WS
hub layers a per-notebook broadcast on top of these
primitives; this file stays storage-focused so unit tests can exercise
the CRDT state machine without an asyncio loop.

Doc shape (locked in 105.1):

* ``cells_order`` (:class:`pycrdt.Array`) — ordered ``cell_uuid``
  list; mutating it is how add / remove / move propagates.
* ``cells_text`` (:class:`pycrdt.Map`) — ``{cell_uuid: Text}`` where
  the Text holds the live source.

The two top-level shared types are declared *before* any
``apply_update`` so the wire format stays consistent across peers
(pycrdt mirrors Y.js — top-level structure must be registered before
binary updates land, otherwise the peers diverge silently).
"""

from __future__ import annotations

import datetime
from typing import Any

from pycrdt import Array, Doc, Map, Text
from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookCrdtState

# Top-level type names baked into the Y.Doc.  Used by both server and
# client (``y-monaco`` binds Monaco models to ``cells_text[uuid]``).
CELLS_ORDER_KEY = "cells_order"
CELLS_TEXT_KEY = "cells_text"

# Compaction thresholds — re-serialise the live Doc once the persisted
# blob crosses :data:`COMPACTION_SIZE_BYTES` or :data:`COMPACTION_TTL`
# elapses since the last compaction.  Sprint 105.8 wires a worker that
# walks every row through :func:`compact`.
COMPACTION_SIZE_BYTES = 256 * 1024
COMPACTION_TTL = datetime.timedelta(hours=24)


def _build_empty_doc() -> Doc:  # pyright: ignore[reportMissingTypeArgument]
    """Construct a fresh Y.Doc with the locked top-level shape.

    Both the server-side replica + every connected client *must* set
    up the same top-level shared types before exchanging binary
    updates; this helper keeps that contract in one place.
    """
    doc = Doc()  # pyright: ignore[reportMissingTypeArgument]
    doc[CELLS_ORDER_KEY] = Array()  # pyright: ignore[reportMissingTypeArgument]
    doc[CELLS_TEXT_KEY] = Map()  # pyright: ignore[reportMissingTypeArgument]
    return doc


def get_or_init_ydoc(
    session: Session,
    *,
    notebook_id: str,
    seed_cells: list[dict[str, Any]] | None = None,
) -> Doc:  # pyright: ignore[reportMissingTypeArgument]
    """Return the live :class:`Doc` for *notebook_id*.

    On a cold cache (no row in ``notebook_crdt_state``) the function
    mints a fresh Doc, seeds it from *seed_cells* if provided (the
    typical caller passes the result of
    :func:`services.notebook._doc.load_document`), persists the
    resulting state, and returns the populated Doc.  Warm-start just
    replays the persisted blob.

    Args:
        session: A SQLAlchemy session.  Caller owns the transaction;
            this function flushes but does not commit.
        notebook_id: 36-char :class:`Notebook` UUID.
        seed_cells: Optional list of cell dicts ``{cell_uuid, source}``
            used to bootstrap the Doc on cold init.  Ignored when a
            row already exists.

    Returns:
        A :class:`pycrdt.Doc` with the locked top-level shape, ready
        for ``apply_update`` calls from the WS hub.

    Raises:
        ValidationError: When *notebook_id* is unknown.
    """
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    row = session.execute(
        select(NotebookCrdtState).where(
            NotebookCrdtState.notebook_id == notebook_id
        )
    ).scalar_one_or_none()
    if row is not None and row.y_doc_blob:
        doc = _build_empty_doc()
        doc.apply_update(row.y_doc_blob)
        return doc
    # Cold init — mint + optionally seed + persist.
    doc = _build_empty_doc()
    if seed_cells:
        _seed_cells_into_doc(doc, seed_cells)
    blob = doc.get_update()
    _upsert_state(session, notebook_id=notebook_id, blob=blob)
    return doc


def _seed_cells_into_doc(
    doc: Doc,  # pyright: ignore[reportMissingTypeArgument]
    cells: list[dict[str, Any]],
) -> None:
    """Push the on-disk cell list into the Doc's top-level structures.

    Each cell needs at minimum ``cell_uuid`` + ``source``; missing
    UUIDs are silently skipped so a partial-load (e.g. the save-path
    reconciler hasn't run yet) cannot corrupt the doc.
    """
    order: Array = doc[CELLS_ORDER_KEY]  # pyright: ignore[reportMissingTypeArgument]
    texts: Map = doc[CELLS_TEXT_KEY]  # pyright: ignore[reportMissingTypeArgument]
    for cell in cells:
        uuid = cell.get("cell_uuid")
        source = cell.get("source") or ""
        if not uuid:
            continue
        order.append(str(uuid))
        texts[str(uuid)] = Text(str(source))


def apply_update(
    session: Session,
    *,
    notebook_id: str,
    update_bytes: bytes,
) -> bytes:
    """Apply an incoming binary update to the persistent replica.

    The function (a) reads the current state blob, (b) applies the
    update to a live Doc, (c) writes the resulting state back as the
    new authoritative blob.  Returns the new blob so the caller (WS
    hub) can opportunistically rebroadcast the freshly-merged state
    to other subscribers, though the typical fanout pattern just
    rebroadcasts the original update bytes.

    Args:
        session: A SQLAlchemy session.
        notebook_id: 36-char notebook UUID.
        update_bytes: Binary update emitted by a client.

    Returns:
        The new full-state blob after merge.

    Raises:
        ValidationError: When the notebook is unknown.
    """  # noqa: DOC502 — delegate raises via get_or_init_ydoc
    doc = get_or_init_ydoc(session, notebook_id=notebook_id)
    doc.apply_update(update_bytes)
    blob = doc.get_update()
    _upsert_state(session, notebook_id=notebook_id, blob=blob)
    return blob


def encode_state_as_update(
    session: Session, *, notebook_id: str
) -> bytes:
    """Return the current blob for an initial-sync push to a client.

    The WS hub calls this on every new connection so the client's
    Doc converges with the server replica before any sync frames
    flow.

    Args:
        session: A SQLAlchemy session.
        notebook_id: 36-char notebook UUID.

    Returns:
        Full-state encoding suitable for the client's
        ``doc.apply_update(blob)``.  Empty bytes when no state has
        ever been persisted (the client then starts from its own
        empty replica and the first save merges them).
    """
    row = session.execute(
        select(NotebookCrdtState).where(
            NotebookCrdtState.notebook_id == notebook_id
        )
    ).scalar_one_or_none()
    if row is None:
        return b""
    return bytes(row.y_doc_blob)


def compact(session: Session, *, notebook_id: str) -> bytes:
    """Re-serialise the live Doc to collapse accumulated updates.

    pycrdt's wire format is append-friendly — every apply_update +
    re-get_update cycle keeps the size monotonic-ish.  Compaction
    rebuilds the blob from the loaded Doc's current state vector so
    storage doesn't grow unbounded.

    Args:
        session: A SQLAlchemy session.
        notebook_id: 36-char notebook UUID.

    Returns:
        The compacted blob.

    Raises:
        ValidationError: When the notebook is unknown.
    """  # noqa: DOC502 — delegate raises via get_or_init_ydoc
    doc = get_or_init_ydoc(session, notebook_id=notebook_id)
    blob = doc.get_update()
    _upsert_state(
        session,
        notebook_id=notebook_id,
        blob=blob,
        mark_compacted=True,
    )
    return blob


def needs_compaction(row: NotebookCrdtState) -> bool:
    """Heuristic gate — ``True`` once a row crosses size or TTL bounds.

    Used by the Sprint 105.8 compaction worker to throttle the work.
    Pure function over the row so the worker can batch decisions
    without hitting the live Doc.
    """
    if len(row.y_doc_blob or b"") >= COMPACTION_SIZE_BYTES:
        return True
    last = row.compacted_at or row.updated_at
    now = datetime.datetime.now(datetime.UTC)
    if now.tzinfo is None or last.tzinfo is None:
        # Tests sometimes round-trip naive timestamps through SQLite;
        # normalise both sides to naive before subtracting to avoid
        # a TypeError that would mask the throttle decision.
        return (now.replace(tzinfo=None) - last.replace(tzinfo=None)) >= COMPACTION_TTL
    return (now - last) >= COMPACTION_TTL


def _upsert_state(
    session: Session,
    *,
    notebook_id: str,
    blob: bytes,
    mark_compacted: bool = False,
) -> NotebookCrdtState:
    """Insert-or-update the sidecar row for *notebook_id*.

    Args:
        session: A SQLAlchemy session.
        notebook_id: 36-char notebook UUID.
        blob: Full-state encoding to persist.
        mark_compacted: When ``True`` (compaction path), stamp
            ``compacted_at`` to ``now()``.

    Returns:
        The persisted row.
    """
    row = session.execute(
        select(NotebookCrdtState).where(
            NotebookCrdtState.notebook_id == notebook_id
        )
    ).scalar_one_or_none()
    now = datetime.datetime.now(datetime.UTC)
    if row is None:
        row = NotebookCrdtState(
            notebook_id=notebook_id,
            y_doc_blob=blob,
            updated_at=now,
            compacted_at=now if mark_compacted else None,
        )
        session.add(row)
    else:
        row.y_doc_blob = blob
        row.updated_at = now
        if mark_compacted:
            row.compacted_at = now
    session.flush()
    return row


def flush_doc(
    session: Session,
    *,
    notebook_id: str,
    doc: Doc,  # pyright: ignore[reportMissingTypeArgument]
) -> bytes:
    """Persist *doc*'s current state without touching the live replica.

    The Sprint 105.2 WS hub holds the authoritative :class:`Doc` in
    memory and edits it directly under the hub's per-notebook lock;
    this helper just snapshots that in-memory replica back to the
    sidecar row.  Distinct from :func:`apply_update` (which builds a
    fresh Doc from disk on every call) so the hot path stays
    in-process and avoids the per-keystroke read-then-write that the
    storage primitive's API shape would force.

    Args:
        session: A SQLAlchemy session.  Caller owns the transaction;
            this function flushes but does not commit.
        notebook_id: 36-char :class:`Notebook` UUID.
        doc: The hub-owned live :class:`pycrdt.Doc` whose current
            state should be persisted.

    Returns:
        The new full-state blob after the write.
    """
    blob = doc.get_update()
    _upsert_state(session, notebook_id=notebook_id, blob=blob)
    return blob


__all__ = [
    "CELLS_ORDER_KEY",
    "CELLS_TEXT_KEY",
    "COMPACTION_SIZE_BYTES",
    "COMPACTION_TTL",
    "apply_update",
    "compact",
    "encode_state_as_update",
    "flush_doc",
    "get_or_init_ydoc",
    "needs_compaction",
]
