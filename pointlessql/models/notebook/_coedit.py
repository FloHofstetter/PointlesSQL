"""CRDT sidecar for real-time co-edit.

Holds the serialised ``pycrdt.Doc`` state per notebook so a fresh WS
subscriber can warm-start from the latest committed state instead of
replaying every update from the beginning of time.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookCrdtState(Base):
    """Sidecar persistence for the Phase-105 Y.Doc per notebook.

    Holds the serialised ``pycrdt.Doc`` state for one notebook so a
    fresh WS subscriber can warm-start from the latest committed
    state instead of replaying every update from the beginning of
    time.  The ``.py`` on disk stays IDE-agnostic (per the
    ``feedback_notebook_py_editability`` rule) — the CRDT lives
    entirely in metadata.

    ``y_doc_blob`` is the output of :meth:`pycrdt.Doc.get_update`
    with no state-vector argument (full state encoding).  Server-side
    load is ``doc = Doc(); doc.apply_update(blob)``; the WS hub
    proxies sync + awareness frames between connected
    clients.  Compaction re-serialises the live Doc
    over the existing blob once it crosses 256 KiB or 24 h.

    Attributes:
        notebook_id: FK to :class:`Notebook` — one row per notebook,
            cascade-delete so removing a notebook drops the state.
        y_doc_blob: Binary state encoding (Y.js compatible).  Empty
            byte string on first init.
        updated_at: Wall-clock of the last update apply / compaction.
        compacted_at: Wall-clock of the last compaction; ``None``
            while no compaction has run yet.
        version: Schema version of the encoding inside the blob.
            Reserved for future migrations of the pycrdt wire format;
            defaults to ``1`` today.
    """

    __tablename__ = "notebook_crdt_state"

    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    y_doc_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    compacted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
