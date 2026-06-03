"""Lifecycle manager for a managed Hermes dashboard subprocess.

PointlesSQL spawns ``hermes dashboard`` as a child process so the
``/hermes/`` Agent tab in :mod:`pointlessql.api.hermes_routes.proxy`
can reverse-proxy its React SPA + chat WebSocket behind the
application's auth layer.  The shape mirrors
:class:`pointlessql.services.mlflow_subprocess.MLflowSubprocess`:
async spawn, HTTP health-poll, graceful SIGTERM-then-SIGKILL stop.

A single Hermes process owns exactly one home directory (its config
and session database), so multi-tenant isolation is expressed by
running several instances, each pinned to a distinct ``HERMES_HOME``
and port.  :class:`HermesInstance` is the unit of one such process;
:class:`pointlessql.services.hermes.manager.HermesInstanceManager`
decides how many to run and which operator each one serves.

The dashboard authenticates ``/api/*`` calls with a pre-shared token
read from ``HERMES_DASHBOARD_SESSION_TOKEN``; the proxy injects that
same token on every forwarded request.  The chat pane (``--tui``) is
a POSIX-only PTY bridge, so it is skipped with a warning on
non-POSIX hosts rather than crashing the launch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import time
from pathlib import Path

import httpx

from pointlessql.exceptions import PointlessSQLError
from pointlessql.types import ErrorCode

_logger = logging.getLogger(__name__)

_HEALTH_POLL_S = 0.5
_SHUTDOWN_GRACE_S = 5.0


class HermesStartupError(PointlessSQLError, RuntimeError):
    """Raised when a Hermes dashboard subprocess fails to come up healthy.

    Dual-parents :class:`PointlessSQLError` (so the centralised
    handler renders it as 503) and :class:`RuntimeError` (so legacy
    ``except RuntimeError`` clauses continue to catch).

    Attributes:
        status_code: Always 503.
        error_code: Always ``ErrorCode.HERMES_STARTUP_ERROR``.
    """

    status_code: int = 503
    error_code: ErrorCode = ErrorCode.HERMES_STARTUP_ERROR


def hermes_available(command: str = "hermes") -> bool:
    """Return True if the ``hermes`` launcher is resolvable on ``PATH``.

    Managed mode shells out to this command; when it is missing the
    lifespan logs a warning and leaves the manager in external-only
    mode so the Agent tab degrades to a clear message instead of
    bringing the whole start-up down.

    Args:
        command: The launcher name or absolute path to probe.

    Returns:
        bool: True when :func:`shutil.which` resolves *command*.
    """
    return shutil.which(command) is not None


class HermesInstance:
    """One managed ``hermes dashboard`` process bound to a home + port.

    Args:
        command: Launcher resolvable on ``PATH`` (``"hermes"``).
        host: Bind host for the dashboard (loopback for managed mode).
        port: Bind port; each instance in a per-operator pool gets its
            own so they never collide.
        token: Pre-shared dashboard session token the proxy injects on
            forwarded requests.
        home: ``HERMES_HOME`` for this process — the only thing that
            isolates one operator's sessions from another's.
        chat_enabled: Launch the POSIX-only chat PTY (``--tui``).
        startup_timeout_seconds: Health-poll deadline before the launch
            is declared failed.
    """

    def __init__(
        self,
        *,
        command: str,
        host: str,
        port: int,
        token: str,
        home: Path,
        chat_enabled: bool,
        startup_timeout_seconds: int,
    ) -> None:
        self.command = command
        self.host = host
        self.port = port
        self.token = token
        self.home = home
        self.chat_enabled = chat_enabled
        self.startup_timeout_seconds = startup_timeout_seconds
        self.proc: asyncio.subprocess.Process | None = None
        # Monotonic stamp bumped on every proxy hit so the manager can
        # reap instances nobody has touched within the idle window.
        self.last_used = time.monotonic()

    @property
    def base_url(self) -> str:
        """HTTP base URL the proxy forwards to."""
        return f"http://{self.host}:{self.port}"

    @property
    def ws_base_url(self) -> str:
        """WebSocket base URL for the chat-PTY bridge."""
        return f"ws://{self.host}:{self.port}"

    def touch(self) -> None:
        """Record activity so the idle reaper keeps this instance alive."""
        self.last_used = time.monotonic()

    async def start(self) -> None:
        """Spawn the dashboard and wait until ``/api/status`` answers 200.

        Raises:
            HermesStartupError: If the subprocess does not respond
                healthy within ``startup_timeout_seconds`` or exits
                early with a non-zero return code.
        """
        self.home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HERMES_DASHBOARD_SESSION_TOKEN"] = self.token
        env["HERMES_HOME"] = str(self.home)

        cmd = [
            self.command,
            "dashboard",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--no-open",
        ]
        want_chat = self.chat_enabled and os.name == "posix"
        if want_chat:
            cmd.append("--tui")
            env["HERMES_DASHBOARD_TUI"] = "1"
        elif self.chat_enabled:
            _logger.warning(
                "Hermes chat pane requested but disabled: the PTY bridge is "
                "POSIX-only and this host is %s",
                os.name,
            )

        _logger.info(
            "Starting Hermes dashboard: host=%s port=%d home=%s chat=%s",
            self.host,
            self.port,
            self.home,
            want_chat,
        )
        self.proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await self._wait_for_health()
        except HermesStartupError:
            await self.stop()
            raise

    async def _wait_for_health(self) -> None:
        """Poll ``/api/status`` until OK or the timeout elapses.

        Raises:
            HermesStartupError: On timeout or early subprocess exit.
        """
        url = f"{self.base_url}/api/status"
        deadline = asyncio.get_event_loop().time() + self.startup_timeout_seconds
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                if self.proc and self.proc.returncode is not None:
                    raise HermesStartupError(
                        f"Hermes dashboard exited early with code {self.proc.returncode}",
                    )
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        _logger.info("Hermes dashboard healthy on port %d", self.port)
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                await asyncio.sleep(_HEALTH_POLL_S)
        raise HermesStartupError(
            f"Hermes dashboard did not become healthy within {self.startup_timeout_seconds}s",
        )

    async def health(self) -> bool:
        """Return True if ``/api/status`` currently answers 200."""
        if not self.proc or self.proc.returncode is not None:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/status")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def stop(self) -> None:
        """Gracefully stop the dashboard subprocess.

        Sends SIGTERM, waits up to :data:`_SHUTDOWN_GRACE_S` seconds
        for clean exit, then escalates to SIGKILL.
        """
        if not self.proc:
            return
        if self.proc.returncode is None:
            try:
                self.proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.proc.wait(), timeout=_SHUTDOWN_GRACE_S)
            except TimeoutError:
                _logger.warning(
                    "Hermes dashboard (pid=%s) did not exit within %.1fs of SIGTERM; "
                    "escalating to SIGKILL",
                    self.proc.pid,
                    _SHUTDOWN_GRACE_S,
                )
                self.proc.kill()
                await self.proc.wait()
        self.proc = None
