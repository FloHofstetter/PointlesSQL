"""Per-tab pyright-langserver subprocess for the native editor.

Phase 12.6 Sprint 61 — the fourth layer of the native notebook
story. Each browser tab that opens the editor also opens a
WebSocket to this service; we spawn one ``pyright-langserver
--stdio`` subprocess per WS connection and proxy LSP JSON-RPC
frames bidirectionally.

Why per-tab (not per-user, not per-notebook):

* **Isolation is cheap.** Pyright starts in ~1–2 s on a warm
  cache and costs ~100 MB resident. Single-user dev use never
  has enough concurrent tabs for shared-subprocess pooling to
  pay off against the added complexity of routing diagnostics
  to the right subscriber.
* **Subprocess lifetime = tab lifetime.** ``shutdown`` runs in
  the WS finally block; no lifespan registry needed. Sprint 63
  retires the JupyterLab iframe but does not touch this file.
* **One workspace per tab.** Pyright takes a single
  ``rootUri`` + workspace folder on ``initialize``; different
  notebooks can safely share one process only if we track per-
  file state ourselves, which the per-tab model avoids.

The WS handler drives the protocol — this service is purely
plumbing (framing + async stdio + subprocess lifecycle).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


_PYRIGHT_COMMAND_NAME = "pyright-langserver"
_STARTUP_ARGS = ["--stdio"]
_SHUTDOWN_TIMEOUT = 2.0


def find_pyright_langserver() -> str | None:
    """Return the absolute path to ``pyright-langserver``, or ``None``.

    The pypi ``pyright`` package installs the binary into the same
    ``.venv/bin`` directory that ``uv run`` adds to ``PATH``, so a
    simple :func:`shutil.which` lookup resolves it in both the dev
    and the Docker runtimes without extra config.

    Returns:
        Absolute path when the binary is on ``PATH``; ``None``
        when pyright is not installed (the WS handler responds with
        a 4404 close code in that case).
    """
    return shutil.which(_PYRIGHT_COMMAND_NAME)


class PyrightSession:
    r"""One ``pyright-langserver --stdio`` subprocess.

    The object is created up front with an async callback that
    fires for every inbound LSP message; :meth:`start` spawns the
    subprocess and kicks off the reader task, :meth:`send` writes
    a JSON-RPC message with the standard ``Content-Length`` frame,
    :meth:`shutdown` tears the subprocess down gracefully.

    LSP framing:

        Content-Length: <N>\r\n\r\n<JSON body of N bytes>

    — same in both directions. Pyright never emits partial
    messages; the reader loop expects the Content-Length header
    to be accurate and reads exactly that many bytes of body.

    Args:
        on_message: Async callback invoked for every parsed
            inbound message. The callback's exceptions are
            logged and swallowed so a broken subscriber does
            not tear the reader loop down.
    """

    def __init__(
        self,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._on_message = on_message
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Launch the subprocess + start the reader loop."""
        binary = find_pyright_langserver()
        if binary is None:
            raise RuntimeError(
                "pyright-langserver not found on PATH — `uv sync` should install it"
            )
        self._proc = await asyncio.create_subprocess_exec(
            binary,
            *_STARTUP_ARGS,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(
            self._read_loop(), name="pyright-lsp-reader"
        )
        logger.info("pyright-langserver started (pid=%d)", self._proc.pid)

    async def _read_loop(self) -> None:
        """Read LSP frames off stdout forever and dispatch each one."""
        assert self._proc is not None
        assert self._proc.stdout is not None
        stdout = self._proc.stdout
        while True:
            try:
                content_length = await _read_headers(stdout)
            except asyncio.IncompleteReadError:
                return  # EOF — subprocess exited
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — malformed header is fatal for this session
                logger.exception("pyright header parse failed")
                return
            if content_length is None:
                return
            try:
                body = await stdout.readexactly(content_length)
            except asyncio.IncompleteReadError:
                return
            try:
                msg = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                logger.exception("pyright body decode failed")
                continue
            try:
                await self._on_message(msg)
            except Exception:  # noqa: BLE001 — subscriber error must not kill the loop
                logger.exception("pyright on_message handler raised")

    async def send(self, message: dict[str, Any]) -> None:
        """Write one JSON-RPC message to pyright's stdin.

        Args:
            message: A JSON-serialisable LSP message (request,
                response, or notification).

        Raises:
            RuntimeError: When the session has not been started
                yet or its subprocess has exited.
        """
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("pyright session not started")
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        await self._proc.stdin.drain()

    async def shutdown(self) -> None:
        """Tear the subprocess down gracefully, SIGTERM + timeout + SIGKILL."""
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        if self._proc is None:
            return
        if self._proc.returncode is not None:
            return
        try:
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=_SHUTDOWN_TIMEOUT)
        except TimeoutError:
            logger.warning("pyright-langserver did not stop — killing")
            self._proc.kill()
            await self._proc.wait()


async def _read_headers(stdout: asyncio.StreamReader) -> int | None:
    """Read LSP headers up to the blank-line terminator.

    Args:
        stdout: Subprocess stdout stream.

    Returns:
        The ``Content-Length`` value as an int, or ``None`` when
        the stream closed cleanly before a header was received.
    """
    content_length: int | None = None
    while True:
        line = await stdout.readline()
        if not line:
            return None
        stripped = line.rstrip(b"\r\n")
        if not stripped:
            break
        name, _, value = stripped.decode("ascii").partition(": ")
        if name.lower() == "content-length":
            try:
                content_length = int(value)
            except ValueError:
                logger.warning("pyright bad Content-Length: %r", value)
    return content_length
