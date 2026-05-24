"""Phase 109 — cross-worker co-edit bus via PG LISTEN/NOTIFY.

Bridges the in-memory Phase-105.2 hub across multiple uvicorn
workers without adding Redis / RabbitMQ / NATS.  Each worker keeps a
single long-lived psycopg async connection in autocommit mode that
``LISTEN coedit_bus``; publishers INSERT a row into
``coedit_bus_messages`` and ``pg_notify('coedit_bus', '<id>:<nb>')``
inside the same transaction so the row is visible by the time other
workers receive the notify.

Wire format on the channel payload is ``"{row_id}:{notebook_uuid}"``
— two columns, colon-separated, both ASCII so PG NOTIFY's encoding
is irrelevant.  The 8000-byte payload limit applies to the channel
payload only; the real frame lives in the ``payload`` BYTEA column,
sidestepping the limit entirely.

Lifecycle is owned by the FastAPI lifespan
(:func:`pointlessql.api._bootstrap._lifespan.make_lifespan`).  On
SQLite installs the bus is never started — :func:`CoeditBus.start`
no-ops, :func:`CoeditBus.publish` short-circuits.  Phase 109's hub
instrumentation (Sprint 109.2) checks ``app.state.coedit_bus is
not None`` before publishing.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.engine import Engine

from pointlessql.models.notebook import CoeditBusMessage

_LOG = logging.getLogger(__name__)

NOTIFY_CHANNEL = "coedit_bus"

# Bounded backoff so a flapping PG connection doesn't busy-loop the
# event loop.  Aligned with the WS client's reconnect ladder so an
# operator sees similar cadence on both sides.
_RECONNECT_BACKOFF_S: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)

# Callback signature: ``async def cb(notebook_uuid: str, payload: bytes,
# source_pid: int) -> None``.  Hub instrumentation registers an instance.
DispatchCallback = Callable[[str, bytes, int], Awaitable[None]]


class CoeditBus:
    """PG LISTEN/NOTIFY pub/sub bridge for the co-edit hub.

    Lifecycle is start/stop tied to the FastAPI lifespan.  Two
    asyncio tasks are owned by the instance: a listener that drains
    ``conn.notifies()`` forever and dispatches each notify to the
    registered callback, and a cleanup loop that sweeps outbox rows
    older than ``ttl_seconds`` every ``cleanup_interval_seconds``.
    The instance is safe to share across hubs — the listener
    callback receives the ``notebook_uuid`` and dispatches into the
    right ``_HUBS[notebook_uuid]`` entry on the receive path.

    Construction binds to a SQLAlchemy sync engine that must point at
    PostgreSQL — :func:`ValueError` is raised for SQLite or any other
    dialect because LISTEN/NOTIFY is a PG-specific primitive.
    ``ttl_seconds`` (default 60) bounds outbox row lifetime;
    ``cleanup_interval_seconds`` (default 30) sets the sweep cadence.
    ``own_pid`` is captured from :func:`os.getpid` at construction and
    used by both the publisher (stamp ``source_pid``) and the listener
    (skip self-loops).
    """

    def __init__(
        self,
        engine: Engine,
        *,
        ttl_seconds: int = 60,
        cleanup_interval_seconds: int = 30,
    ) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError(
                f"CoeditBus requires PostgreSQL; got dialect "
                f"{engine.dialect.name!r}"
            )
        self.engine: Engine = engine
        self.ttl_seconds: int = ttl_seconds
        self.cleanup_interval_seconds: int = cleanup_interval_seconds
        self.own_pid: int = os.getpid()
        self._dsn: str = self._resolve_dsn(engine)
        self._listener_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._dispatch_callback: DispatchCallback | None = None
        self._listener_ready = asyncio.Event()
        self._closing = False

    @staticmethod
    def _resolve_dsn(engine: Engine) -> str:
        """Return a libpq-compatible DSN for the bound engine.

        SQLAlchemy URLs include the driver name
        (``postgresql+psycopg://``) which libpq does not understand.
        Strip the ``+driver`` portion before handing to
        :func:`psycopg.AsyncConnection.connect`.
        """
        url = engine.url
        # Render without the password masking SQLAlchemy applies in
        # __repr__; we need the real password to connect.
        rendered = url.render_as_string(hide_password=False)
        if rendered.startswith("postgresql+"):
            # ``postgresql+psycopg://...`` → ``postgresql://...``
            scheme_end = rendered.index("://")
            return "postgresql" + rendered[scheme_end:]
        return rendered

    def set_dispatch_callback(self, callback: DispatchCallback) -> None:
        """Register the per-frame dispatch callback.

        The hub side (Sprint 109.2) calls this once at lifespan
        startup with a coroutine that routes incoming frames into
        the local ``_HUBS`` dispatch path.  Idempotent — overwriting
        is supported but not expected.

        Args:
            callback: ``async def cb(notebook_uuid, payload,
                source_pid) -> None``.
        """
        self._dispatch_callback = callback

    async def start(self) -> None:
        """Spawn the listener + cleanup tasks.

        Does not block on the initial LISTEN handshake — the
        listener task takes care of (re)connecting.  Wait on
        :attr:`_listener_ready` if a caller needs to know the
        socket is up before publishing.
        """
        if self._listener_task is not None:
            return
        self._closing = False
        self._listener_task = asyncio.create_task(
            self._listener_loop(), name="coedit-bus-listener"
        )
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="coedit-bus-cleanup"
        )

    async def stop(self) -> None:
        """Cancel the background tasks and drain them.

        Safe to call multiple times.  Used by the lifespan teardown.
        """
        self._closing = True
        for task in (self._listener_task, self._cleanup_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._listener_task = None
        self._cleanup_task = None

    async def publish(
        self,
        notebook_uuid: str,
        payload: bytes,
    ) -> None:
        """Persist + announce a frame for cross-worker fanout.

        Inserts one row into ``coedit_bus_messages`` and emits
        ``pg_notify(NOTIFY_CHANNEL, '<id>:<notebook_uuid>')`` in
        the same transaction so the row is committed before the
        notify reaches any other worker.  Source PID is captured
        from :attr:`own_pid` so listeners can skip self-loops.

        Failures are logged + swallowed: the local broadcast has
        already happened by the time we get here, so a transient PG
        outage costs cross-worker consistency but not the local
        editor experience.  CRDT re-converges on the next successful
        update.

        Args:
            notebook_uuid: Target notebook id (36-char UUID).
            payload: Tag-prefixed wire bytes — same frame the WS
                relays to local subscribers.
        """
        try:
            await asyncio.to_thread(self._publish_sync, notebook_uuid, payload)
        except Exception:  # noqa: BLE001 — best-effort; local broadcast already done
            _LOG.exception(
                "coedit-bus: publish failed for nb=%s (%d bytes)",
                notebook_uuid,
                len(payload),
            )

    def _publish_sync(self, notebook_uuid: str, payload: bytes) -> None:
        """Sync body of :meth:`publish`, run in a thread executor.

        Kept separate so unit tests can exercise the SQL path
        without an asyncio loop.
        """
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(CoeditBusMessage)
                .values(
                    notebook_uuid=notebook_uuid,
                    payload=payload,
                    source_pid=self.own_pid,
                )
                .returning(CoeditBusMessage.id)
            )
            row_id = int(result.scalar_one())
            conn.execute(
                text("SELECT pg_notify(:ch, :pl)"),
                {"ch": NOTIFY_CHANNEL, "pl": f"{row_id}:{notebook_uuid}"},
            )

    async def _listener_loop(self) -> None:
        """Drain notifies from a persistent async connection forever.

        Reconnects with bounded backoff on transient errors so a
        PG restart doesn't kill the worker.  Each NOTIFY is parsed
        into ``(row_id, notebook_uuid)``; the row is fetched and
        the registered :attr:`_dispatch_callback` is invoked.
        Rows authored by ``own_pid`` are skipped (self-loops).
        """
        attempt = 0
        while not self._closing:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._dsn, autocommit=True
                ) as conn:
                    await conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
                    self._listener_ready.set()
                    attempt = 0
                    async for notify in conn.notifies():
                        if self._closing:
                            return
                        await self._handle_notify(notify.payload)
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — reconnect on any PG error
                if self._closing:
                    return
                self._listener_ready.clear()
                delay = _RECONNECT_BACKOFF_S[
                    min(attempt, len(_RECONNECT_BACKOFF_S) - 1)
                ]
                attempt += 1
                _LOG.exception(
                    "coedit-bus: listener disconnected; reconnect in %.1fs",
                    delay,
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    return

    async def _handle_notify(self, channel_payload: str) -> None:
        """Decode one ``<id>:<notebook_uuid>`` notify into a dispatch.

        Skips notifies whose payload doesn't match the expected
        shape, whose row has TTL'd out before the listener got
        here, or whose ``source_pid`` matches our own.
        """
        try:
            row_id_str, _nb_uuid_hint = channel_payload.split(":", 1)
            row_id = int(row_id_str)
        except (ValueError, AttributeError):
            _LOG.warning(
                "coedit-bus: malformed notify payload %r", channel_payload
            )
            return

        # Fetch the row payload in a thread so the listener loop's
        # event loop stays responsive to other notifies.
        try:
            row = await asyncio.to_thread(self._fetch_row, row_id)
        except Exception:  # noqa: BLE001 — best-effort; CRDT re-converges
            _LOG.exception("coedit-bus: fetch failed for row %d", row_id)
            return
        if row is None:
            # Row was TTL-cleaned between NOTIFY and SELECT.  Rare.
            return
        if row.source_pid == self.own_pid:
            return
        callback = self._dispatch_callback
        if callback is None:
            return
        try:
            await callback(row.notebook_uuid, row.payload, row.source_pid)
        except Exception:  # noqa: BLE001 — keep listener alive on callback bug
            _LOG.exception(
                "coedit-bus: dispatch callback raised for nb=%s",
                row.notebook_uuid,
            )

    def _fetch_row(self, row_id: int) -> CoeditBusMessage | None:
        """Fetch a single outbox row by id (synchronous)."""
        with self.engine.connect() as conn:
            return conn.execute(
                select(CoeditBusMessage).where(CoeditBusMessage.id == row_id)
            ).scalar_one_or_none()

    async def _cleanup_loop(self) -> None:
        """Sweep expired outbox rows on a fixed cadence."""
        while not self._closing:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
            except asyncio.CancelledError:
                return
            try:
                deleted = await asyncio.to_thread(self._cleanup_once)
            except Exception:  # noqa: BLE001 — keep looping on transient errors
                _LOG.exception("coedit-bus: cleanup sweep failed")
                continue
            if deleted:
                _LOG.debug("coedit-bus: cleaned %d expired outbox rows", deleted)

    def _cleanup_once(self) -> int:
        """Delete outbox rows older than :attr:`ttl_seconds`.

        Returns:
            Number of rows removed.
        """
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            seconds=self.ttl_seconds
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(CoeditBusMessage).where(CoeditBusMessage.ts < cutoff)
            )
            return int(result.rowcount or 0)

    def status_snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot for the admin endpoint.

        Includes feature-flag derived state, listener task health,
        and a coarse inflight row count so an operator can spot a
        wedged cleanup loop.
        """
        with self.engine.connect() as conn:
            inflight = int(
                conn.execute(
                    select(func.count()).select_from(CoeditBusMessage)
                ).scalar_one()
            )
        listener_alive = (
            self._listener_task is not None
            and not self._listener_task.done()
        )
        cleanup_alive = (
            self._cleanup_task is not None
            and not self._cleanup_task.done()
        )
        return {
            "own_pid": self.own_pid,
            "ttl_seconds": self.ttl_seconds,
            "cleanup_interval_seconds": self.cleanup_interval_seconds,
            "listener_alive": listener_alive,
            "listener_ready": self._listener_ready.is_set(),
            "cleanup_alive": cleanup_alive,
            "inflight_outbox_rows": inflight,
        }
