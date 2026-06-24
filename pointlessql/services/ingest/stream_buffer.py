"""In-process micro-batch buffer for the direct-write stream API.

The stream routes accept small JSON row batches at request rate;
writing each request straight to Delta would produce one commit (and
one parquet file) per request.  :class:`StreamBuffer` decouples the
two rates: rows accumulate per target FQN and flush as one
``deltalake.write_deltalake(mode="append", schema_mode="merge")``
commit when a key reaches ``max_rows`` or its oldest row exceeds
``max_age_seconds`` (a lazily-started once-per-second ticker task
handles the age policy).

Durability: the buffer is process-memory only — rows accepted but not
yet flushed are lost on a crash.  Producers that need stronger
guarantees should call the force-flush endpoint after their batch.
On a flush *failure* the rows stay buffered and are retried on the
next tick / flush, so transient storage errors don't drop data.

Concurrency: buffer *state* (the per-key dicts) is guarded by one
:class:`asyncio.Lock`, but the blocking Delta write runs *outside* that
lock — the key's rows are popped under the lock, then dispatched through
:func:`pointlessql.services._executor.run_sync` with the lock released,
so a slow or stalled write to one table no longer wedges appends to
every other key (or the age-flush ticker).  A failed write merges its
rows back ahead of anything a concurrent append enqueued in the
meantime, so the retry preserves order and drops nothing.

Tuning currently comes from the two module constants below (or ctor
params); folding them into ``Settings`` as a nested
``BaseSettings`` group is left for the main session.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

# Flush policy defaults — ctor params override; settings-ification is
# a follow-up (see module docstring).
DEFAULT_MAX_ROWS = 500
DEFAULT_MAX_AGE_SECONDS = 5.0

_TICK_SECONDS = 1.0


def _append_rows_to_delta(storage_location: str, rows: list[dict[str, Any]]) -> None:
    """Append *rows* to the Delta table at *storage_location*.

    Blocking — callers dispatch through ``run_sync``.  Uses the same
    ``deltalake`` append the ingest pull plane lands on, with
    ``schema_mode="merge"`` so events that grow new fields evolve the
    table schema additively instead of failing the flush.

    Args:
        storage_location: Delta table storage URI.
        rows: JSON-shaped row dicts to append.
    """
    import deltalake
    import pandas as pd

    frame = pd.DataFrame(rows)
    deltalake.write_deltalake(storage_location, frame, mode="append", schema_mode="merge")


@dataclass(slots=True)
class _KeyBuffer:
    """Pending rows for one target FQN.

    Attributes:
        storage_location: Delta URI the rows flush to (refreshed on
            every append so a re-registered table picks up its new
            location).
        rows: Accumulated row dicts.
        oldest_monotonic: ``time.monotonic()`` of the first buffered
            row — drives the age-based flush.
    """

    storage_location: str
    rows: list[dict[str, Any]] = field(default_factory=lambda: [])
    oldest_monotonic: float = 0.0


class StreamBuffer:
    """Per-FQN row buffer with size- and age-triggered Delta flushes.

    One instance lives on ``app.state.ingest_stream_buffer`` (created
    lazily by :func:`get_stream_buffer`); a lifespan teardown hook
    should call :meth:`shutdown` so buffered rows flush on exit.

    Args:
        max_rows: Flush a key as soon as it holds this many rows.
        max_age_seconds: Flush a key once its oldest row is this old.
    """

    def __init__(
        self,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        self._max_rows = int(max_rows)
        self._max_age_seconds = float(max_age_seconds)
        self._buffers: dict[str, _KeyBuffer] = {}
        self._lock = asyncio.Lock()
        self._ticker: asyncio.Task[None] | None = None

    async def append(self, fqn: str, storage_location: str, rows: list[dict[str, Any]]) -> int:
        """Buffer *rows* for *fqn*, flushing if the size cap is hit.

        Args:
            fqn: Three-part target table name (the buffer key).
            storage_location: Delta URI resolved by the caller (the
                route owns the UC lookup + privilege check).
            rows: Row dicts to enqueue.

        Returns:
            Rows still buffered for *fqn* after the call — ``0`` when
            the append tripped the size flush.
        """
        async with self._lock:
            self._ensure_ticker()
            buf = self._buffers.get(fqn)
            if buf is None:
                buf = _KeyBuffer(storage_location=storage_location)
                self._buffers[fqn] = buf
            if not buf.rows:
                buf.oldest_monotonic = time.monotonic()
            buf.storage_location = storage_location
            buf.rows.extend(rows)
            if len(buf.rows) < self._max_rows:
                return len(buf.rows)
            to_write = self._pop_locked(fqn)
        # Size cap tripped — write the detached rows with the lock released.
        if to_write is not None:
            await self._write_buffer(fqn, to_write)
        return 0

    async def flush(self, fqn: str) -> int:
        """Force-flush one key.

        Args:
            fqn: Buffer key to flush.

        Returns:
            Number of rows written (``0`` when nothing was buffered).
        """
        async with self._lock:
            to_write = self._pop_locked(fqn)
        if to_write is None:
            return 0
        return await self._write_buffer(fqn, to_write)

    async def flush_all(self) -> int:
        """Force-flush every key; returns the total rows written.

        Returns:
            Total number of rows written across all keys.
        """
        async with self._lock:
            pending = [(fqn, self._pop_locked(fqn)) for fqn in list(self._buffers)]
        total = 0
        for fqn, buf in pending:
            if buf is not None:
                total += await self._write_buffer(fqn, buf)
        return total

    def buffered_rows(self, fqn: str) -> int:
        """Return the number of rows currently buffered for *fqn*.

        Args:
            fqn: Buffer key to inspect.

        Returns:
            Pending row count (``0`` for unknown keys).
        """
        buf = self._buffers.get(fqn)
        return len(buf.rows) if buf is not None else 0

    async def shutdown(self) -> None:
        """Stop the ticker and flush every remaining key.

        Flush failures are logged and swallowed — shutdown must not
        raise out of the lifespan teardown.
        """
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
            self._ticker = None
        async with self._lock:
            pending = [(fqn, self._pop_locked(fqn)) for fqn in list(self._buffers)]
        for fqn, buf in pending:
            if buf is None:
                continue
            try:
                await self._write_buffer(fqn, buf)
            except Exception:  # noqa: BLE001 — best-effort drain
                logger.exception("ingest stream: shutdown flush failed for %s", fqn)

    def _pop_locked(self, fqn: str) -> _KeyBuffer | None:
        """Detach a key's buffer for an off-lock write; caller holds the lock.

        Removing the entry under the lock means a concurrent append for
        the same key starts a fresh buffer, so the popped rows are owned
        exclusively by the subsequent :meth:`_write_buffer` call.

        Args:
            fqn: Buffer key to detach.

        Returns:
            The detached :class:`_KeyBuffer`, or ``None`` when the key was
            absent or empty (its entry is dropped either way).
        """
        buf = self._buffers.pop(fqn, None)
        if buf is None or not buf.rows:
            return None
        return buf

    async def _write_buffer(self, fqn: str, buf: _KeyBuffer) -> int:
        """Append a detached buffer's rows to Delta without holding the lock.

        Runs the blocking ``write_deltalake`` through ``run_sync`` with the
        state lock released, so a slow write does not block appends to other
        keys.  On failure the rows are merged back ahead of anything a
        concurrent append enqueued in the meantime and the error is
        re-raised, so the rows retry on the next tick / flush.

        Args:
            fqn: Buffer key the rows belong to.
            buf: The detached buffer returned by :meth:`_pop_locked`.

        Returns:
            Number of rows written.

        Raises:
            Exception: Whatever ``write_deltalake`` raised — re-raised after
                the rows are merged back for retry.
        """
        try:
            await run_sync(_append_rows_to_delta, buf.storage_location, buf.rows)
        except Exception:  # noqa: BLE001 — re-raised after restoring rows
            async with self._lock:
                existing = self._buffers.get(fqn)
                if existing is None:
                    self._buffers[fqn] = buf
                else:
                    # Failed rows go first so the original order is kept.
                    buf.rows.extend(existing.rows)
                    existing.rows = buf.rows
                    existing.oldest_monotonic = buf.oldest_monotonic
            raise
        flushed = len(buf.rows)
        logger.info("ingest stream: flushed %d row(s) to %s", flushed, fqn)
        return flushed

    def _ensure_ticker(self) -> None:
        """Start the once-per-second age-flush task if not running."""
        if self._ticker is None or self._ticker.done():
            self._ticker = asyncio.get_running_loop().create_task(self._tick_loop())

    async def _tick_loop(self) -> None:
        """Flush aged keys forever; failures log and retry next tick."""
        while True:
            await asyncio.sleep(_TICK_SECONDS)
            try:
                await self._flush_aged()
            except Exception:  # noqa: BLE001 — rows stay buffered for retry
                logger.exception("ingest stream: aged flush failed; will retry")

    async def _flush_aged(self) -> None:
        """Flush every key whose oldest row exceeds the age cap."""
        now = time.monotonic()
        async with self._lock:
            pending: list[tuple[str, _KeyBuffer]] = []
            for fqn in list(self._buffers):
                buf = self._buffers[fqn]
                if buf.rows and now - buf.oldest_monotonic >= self._max_age_seconds:
                    popped = self._pop_locked(fqn)
                    if popped is not None:
                        pending.append((fqn, popped))
        for fqn, popped in pending:
            await self._write_buffer(fqn, popped)


def get_stream_buffer(app: Any) -> StreamBuffer:
    """Return the app's stream buffer, creating it on first use.

    Args:
        app: The FastAPI app (for ``app.state``).

    Returns:
        The process-global :class:`StreamBuffer`.
    """
    buffer: StreamBuffer | None = getattr(app.state, "ingest_stream_buffer", None)
    if buffer is None:
        buffer = StreamBuffer()
        app.state.ingest_stream_buffer = buffer
    return buffer
