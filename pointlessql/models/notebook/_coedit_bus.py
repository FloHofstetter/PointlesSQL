"""Cross-worker co-edit bus outbox.

Outbox table that lets the otherwise single-process
co-edit hub fan frames out to other uvicorn workers without a
new infrastructure dependency.  Each publish writes one row +
emits a PG ``NOTIFY`` carrying the row id; remote workers receive
the notify, fetch the payload, and replay it into their own local
hub.  PG-only — SQLite installs stay single-worker and never
populate this table.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class CoeditBusMessage(Base):
    """One cross-worker co-edit frame, durable for ~60 s.

    The co-edit hub holds the live :class:`pycrdt.Doc` in the
    uvicorn worker that first claimed it.  Once a second worker is
    online (``POINTLESSQL_COEDIT_BUS_ENABLED=1`` + multiple uvicorn
    workers), updates from one worker must reach editors on the
    other — that fanout rides this outbox.  The publisher writes a
    row + emits ``pg_notify('coedit_bus', '<id>:<notebook_uuid>')``;
    every other worker's listener decodes, fetches, and broadcasts
    to its own local subscribers.

    ``source_pid`` lets the same publisher's own listener skip the
    self-loop without relying on connection identity.  ``ts`` powers
    the 60 s TTL cleanup loop — the table never grows unbounded, and
    a worker that briefly dropped offline can still replay the last
    ~60 s of frames on reconnect.  Wrap-around or longer outages
    rely on the CRDT sync_step1/2 handshake to re-converge.

    Attributes:
        id: BigInt autoincrement PK; encoded into the NOTIFY payload
            so listeners can ``SELECT ... WHERE id = $1``.
        notebook_uuid: 36-char :class:`Notebook` id this frame belongs
            to.  Used by listeners to skip frames for notebooks they
            don't currently host (no local hub).
        payload: Raw wire bytes — same tag-prefixed frame the WS
            handler relays today.  ``BYTEA`` on PG.
        source_pid: ``os.getpid()`` of the publishing worker.
            Lookup-table for self-loop suppression at the listener.
        ts: Wall-clock when the row was inserted.  Index column for
            the TTL cleanup loop.
    """

    __tablename__ = "coedit_bus_messages"

    __table_args__ = (
        Index("ix_coedit_bus_ts", "ts"),
        Index("ix_coedit_bus_notebook_ts", "notebook_uuid", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notebook_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_pid: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
