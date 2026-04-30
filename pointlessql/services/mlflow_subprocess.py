"""Lifecycle manager for the embedded MLflow Tracking server (Phase 21.0).

PointlesSQL spawns ``mlflow server`` as a managed sub-process so the
``/mlflow/`` UI tab in :mod:`pointlessql.api.mlflow_proxy` can forward
requests to it behind the application's auth layer. The pattern
mirrors :mod:`pointlessql.services.kernel_session.session` (the
existing async-subprocess vendor), but with HTTP health-polling and
PID-file persistence because MLflow is a long-running HTTP server,
not an ephemeral kernel.

The subprocess is wired up in
:func:`pointlessql.api.main.lifespan` only when both
``settings.mlflow.enabled`` is true *and* the optional ``mlflow``
package is importable (``pip install pointlessql[ml]``). Anything
that fails the optional-extra check goes through
:func:`mlflow_available` to keep the route surface honest about what
the operator can use.

Boot-time config flow:

1. Read ``MLflowSettings`` to get ``port`` + the three optional URI
   overrides (``backend_store_uri`` / ``artifact_root`` /
   ``registry_uri``).
2. Resolve URI defaults via :meth:`MLflowSubprocess._derive_uris`.
3. Spawn ``python -m mlflow server`` with the derived URIs as CLI
   args + the ``MLFLOW_BACKEND_STORE_URI`` / ``MLFLOW_DEFAULT_ARTIFACT_ROOT``
   env vars (MLflow accepts both as long as they agree).
4. Poll ``GET /health`` with a 30-second deadline.
5. Write a PID file so subsequent PointlesSQL starts can detect a
   zombie subprocess from a previous crash.

Shutdown is graceful SIGTERM with a 5-second grace period before
SIGKILL; the PID file is removed on clean exit.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from pointlessql.settings import MLflowSettings

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

_PID_FILE_NAME = "mlflow.pid"
_HEALTH_TIMEOUT_S = 30.0
_HEALTH_POLL_S = 0.5
_SHUTDOWN_GRACE_S = 5.0


class MLflowStartupError(RuntimeError):
    """Raised when the MLflow subprocess fails to come up healthy."""


@functools.lru_cache(maxsize=1)
def mlflow_available() -> bool:
    """Return True if the optional ``mlflow`` package is importable.

    Cached because the import can be slow (numpy + pandas + sklearn
    cascade). Operators install via ``pip install pointlessql[ml]``;
    when the package is missing, callers (notably
    :func:`pointlessql.api.main.lifespan` and the ``/mlflow/`` page
    route) skip the subprocess + return a 404 / friendly message.

    Returns:
        bool: True if ``import mlflow`` succeeds, else False.
    """
    import importlib.util
    return importlib.util.find_spec("mlflow") is not None


class MLflowSubprocess:
    """Async-managed ``mlflow server`` process.

    Pattern-mirrors
    :class:`pointlessql.services.kernel_session.session.KernelSession`'s
    async-spawn-and-wait-for-ready shape, but adapted for an HTTP
    server: health-check is a polled HTTP probe rather than a
    ZMQ ``wait_for_ready`` call, and the process is expected to
    outlive the spawning context (so we own a PID file in case the
    parent crashes mid-run).

    Attributes:
        settings: The :class:`MLflowSettings` used to derive URIs and
            the bind port.
        soyuz_url: The base URL of the running soyuz-catalog server,
            used to construct the registry URI when none is set
            explicitly.
        cwd: Process CWD used to anchor relative URI defaults.
        proc: The :class:`asyncio.subprocess.Process` once started,
            or ``None`` until :meth:`start` succeeds.
    """

    def __init__(
        self,
        settings: MLflowSettings,
        soyuz_url: str,
        cwd: Path | None = None,
    ) -> None:
        """Initialize the subprocess manager.

        Args:
            settings: MLflow-specific configuration block.
            soyuz_url: Base URL of soyuz (e.g. ``http://127.0.0.1:8080``);
                used when ``settings.registry_uri`` is None.
            cwd: Working directory for relative-path URI defaults;
                defaults to ``Path.cwd()``.
        """
        self.settings = settings
        self.soyuz_url = soyuz_url
        self.cwd = cwd or Path.cwd()
        self.proc: asyncio.subprocess.Process | None = None

    def _derive_uris(self) -> tuple[str, str, str]:
        """Compute the three MLflow URIs from settings + soyuz URL.

        Returns:
            tuple[str, str, str]: ``(backend_store_uri, artifact_root, registry_uri)``.
        """
        backend = self.settings.backend_store_uri or "sqlite:///./mlflow.db"
        artifact_root = (
            self.settings.artifact_root
            or f"file://{(self.cwd / 'mlflow_artifacts').resolve()}"
        )
        # MLflow's UC-OSS scheme is `uc:` followed by the bare HTTP URL,
        # not `uc-oss:` (see uc_oss_rest_store.py + Phase 21.1's diff).
        registry = self.settings.registry_uri or f"uc:{self.soyuz_url}"
        return backend, artifact_root, registry

    @property
    def pid_file(self) -> Path:
        """Path to the PID file used for crash-recovery."""
        return self.cwd / _PID_FILE_NAME

    async def start(self) -> None:
        """Spawn ``mlflow server`` and wait until ``/health`` is OK.

        Raises:
            MLflowStartupError: If the subprocess does not respond
                healthy within :data:`_HEALTH_TIMEOUT_S` seconds.
        """
        backend, artifact_root, registry = self._derive_uris()
        env = os.environ.copy()
        env["MLFLOW_BACKEND_STORE_URI"] = backend
        env["MLFLOW_DEFAULT_ARTIFACT_ROOT"] = artifact_root

        cmd = [
            sys.executable,
            "-m",
            "mlflow",
            "server",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.settings.port),
            "--backend-store-uri",
            backend,
            "--default-artifact-root",
            artifact_root,
            "--registry-store-uri",
            registry,
        ]
        _logger.info(
            "Starting MLflow subprocess: port=%d backend=%s artifact_root=%s registry=%s",
            self.settings.port,
            backend,
            artifact_root,
            registry,
        )
        self.proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.pid_file.write_text(str(self.proc.pid))
        try:
            await self._wait_for_health()
        except MLflowStartupError:
            await self.stop()
            raise

    async def _wait_for_health(self) -> None:
        """Poll ``/health`` until OK or the timeout elapses.

        Raises:
            MLflowStartupError: If the subprocess fails to become
                healthy in time, or exits early with a non-zero
                returncode.
        """
        url = f"http://127.0.0.1:{self.settings.port}/health"
        deadline = asyncio.get_event_loop().time() + _HEALTH_TIMEOUT_S
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                if self.proc and self.proc.returncode is not None:
                    raise MLflowStartupError(
                        f"MLflow exited early with code {self.proc.returncode}",
                    )
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        _logger.info("MLflow subprocess healthy on port %d", self.settings.port)
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                await asyncio.sleep(_HEALTH_POLL_S)
        raise MLflowStartupError(
            f"MLflow subprocess did not become healthy within {_HEALTH_TIMEOUT_S}s",
        )

    async def health(self) -> bool:
        """Return True if ``/health`` currently answers 200."""
        if not self.proc or self.proc.returncode is not None:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"http://127.0.0.1:{self.settings.port}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def stop(self) -> None:
        """Gracefully stop the MLflow subprocess.

        Sends SIGTERM, waits up to :data:`_SHUTDOWN_GRACE_S` seconds
        for clean exit, then escalates to SIGKILL. Removes the PID
        file on exit.
        """
        if not self.proc:
            return
        if self.proc.returncode is None:
            try:
                self.proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.proc.wait(), timeout=_SHUTDOWN_GRACE_S)
            except asyncio.TimeoutError:
                _logger.warning(
                    "MLflow subprocess (pid=%s) did not exit within %.1fs of SIGTERM; "
                    "escalating to SIGKILL",
                    self.proc.pid,
                    _SHUTDOWN_GRACE_S,
                )
                self.proc.kill()
                await self.proc.wait()
        try:
            self.pid_file.unlink()
        except FileNotFoundError:
            pass
        self.proc = None
