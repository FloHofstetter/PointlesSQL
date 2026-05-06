"""Lifecycle manager for the embedded dbt-docs subprocess.

PointlesSQL spawns ``dbt docs serve`` as a managed sub-process so the
``/dbt`` UI tab in :mod:`pointlessql.api.dbt_html_routes` can embed
the dbt-docs UI through the reverse proxy in
:mod:`pointlessql.api.dbt_proxy`.  The pattern mirrors
:mod:`pointlessql.services.mlflow_subprocess` — async spawn,
HTTP health-poll, PID file for crash detection, SIGTERM-then-SIGKILL
shutdown.

Two preconditions must hold for the spawn to actually run:

1. ``settings.dbt.enabled`` must be true.
2. The optional ``dbt-duckdb`` dependency must be importable
   (``pip install pointlessql[dbt]`` / ``uv sync --extra dbt``).
3. ``settings.dbt.project_dir`` must exist *and* contain a compiled
   ``target/manifest.json``.  ``dbt docs serve`` refuses to start
   without one — there is nothing to serve.  When the manifest is
   missing we log an info message and leave ``proc=None`` so the
   ``/dbt`` page can render a friendly "no project compiled yet"
   banner instead of a 5xx.

The third precondition keeps Sprint 36.1 useful even when no dbt
project has been authored yet: the lifespan hook does not block
startup on a missing project, and the page surfaces the gap clearly.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import signal
from pathlib import Path

import httpx

from pointlessql.settings import DBTSettings

_logger = logging.getLogger(__name__)

_PID_FILE_NAME = "dbt_docs.pid"
_HEALTH_TIMEOUT_S = 30.0
_HEALTH_POLL_S = 0.5
_SHUTDOWN_GRACE_S = 5.0


class DBTStartupError(RuntimeError):
    """Raised when the dbt-docs subprocess fails to come up healthy."""


@functools.lru_cache(maxsize=1)
def dbt_duckdb_available() -> bool:
    """Return True if ``dbt-duckdb`` is importable.

    Cached because the import drags in the full dbt-core graph and is
    not free.  Operators install via ``pip install pointlessql[dbt]``;
    when missing, the lifespan skips the subprocess and the ``/dbt``
    page renders the install hint.

    Returns:
        bool: True if both ``dbt`` and ``dbt.adapters.duckdb`` import
            successfully, else False.
    """
    import importlib.util

    return (
        importlib.util.find_spec("dbt") is not None
        and importlib.util.find_spec("dbt.adapters.duckdb") is not None
    )


class DBTSubprocess:
    """Async-managed ``dbt docs serve`` process.

    Mirrors :class:`pointlessql.services.mlflow_subprocess.MLflowSubprocess`'s
    spawn-and-wait-for-ready shape.  The ``project_dir`` and
    ``profiles_dir`` resolve to absolute paths at construction time so
    the subprocess works regardless of which directory PointlesSQL was
    started from.

    Args:
        settings: dbt-specific configuration block; drives the bind
            port, project dir, profiles dir, and target name.
        cwd: Working directory anchor for relative-path defaults;
            defaults to the resolved repo root.  Tests override this
            to point at a fixture project.
    """

    def __init__(
        self,
        settings: DBTSettings,
        cwd: Path | None = None,
    ) -> None:
        self.settings = settings
        self.cwd = (cwd or Path.cwd()).resolve()
        self.proc: asyncio.subprocess.Process | None = None

    @property
    def project_dir(self) -> Path:
        """Resolve ``settings.project_dir`` against ``self.cwd``."""
        p = self.settings.project_dir
        return p if p.is_absolute() else (self.cwd / p).resolve()

    @property
    def profiles_dir(self) -> Path:
        """Resolve ``settings.profiles_dir`` against ``self.cwd``."""
        p = self.settings.profiles_dir
        return p if p.is_absolute() else (self.cwd / p).resolve()

    @property
    def manifest_path(self) -> Path:
        """Path to ``target/manifest.json`` under the project dir."""
        return self.project_dir / "target" / "manifest.json"

    @property
    def pid_file(self) -> Path:
        """Path to the PID file used for crash-recovery."""
        return self.cwd / _PID_FILE_NAME

    def project_ready(self) -> bool:
        """Return True if the project has a compiled manifest.

        ``dbt docs serve`` requires ``target/manifest.json`` to exist;
        without it the server refuses to start.  Callers (the lifespan
        hook) check this before spawning so a freshly-cloned repo
        without a compiled dbt project does not surface as a noisy
        startup error.

        Returns:
            bool: True if the manifest is present, else False.
        """
        return self.project_dir.is_dir() and self.manifest_path.is_file()

    async def start(self) -> None:
        """Spawn ``dbt docs serve`` and wait until the HTTP root responds.

        Raises:
            DBTStartupError: If the subprocess does not respond within
                :data:`_HEALTH_TIMEOUT_S` seconds, or if the project
                dir / manifest preconditions are not met.
        """
        if not self.project_ready():
            raise DBTStartupError(
                f"dbt project not ready: {self.manifest_path} missing. "
                "Run `dbt compile` or `dbt build` first.",
            )

        env = os.environ.copy()
        cmd = [
            "dbt",
            "docs",
            "serve",
            "--port",
            str(self.settings.docs_port),
            "--host",
            "127.0.0.1",
            "--no-browser",
            "--profiles-dir",
            str(self.profiles_dir),
            "--project-dir",
            str(self.project_dir),
            "--target",
            self.settings.target,
        ]
        _logger.info(
            "Starting dbt-docs subprocess: port=%d project_dir=%s target=%s",
            self.settings.docs_port,
            self.project_dir,
            self.settings.target,
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
        except DBTStartupError:
            await self.stop()
            raise

    async def _wait_for_health(self) -> None:
        """Poll the dbt-docs HTTP root until it answers 200.

        ``dbt docs serve`` does not expose a dedicated ``/health``
        endpoint — it serves the static SPA from ``/`` plus a few
        ``/static/...`` assets.  A 200 on ``/`` is therefore the
        readiness signal we use, matching what the iframe will request
        first.

        Raises:
            DBTStartupError: If the subprocess fails to become healthy
                in time, or exits early with a non-zero returncode.
        """
        url = f"http://127.0.0.1:{self.settings.docs_port}/"
        deadline = asyncio.get_event_loop().time() + _HEALTH_TIMEOUT_S
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_event_loop().time() < deadline:
                if self.proc and self.proc.returncode is not None:
                    raise DBTStartupError(
                        f"dbt-docs exited early with code {self.proc.returncode}",
                    )
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        _logger.info(
                            "dbt-docs subprocess healthy on port %d",
                            self.settings.docs_port,
                        )
                        return
                except httpx.ConnectError, httpx.ReadTimeout:
                    pass
                await asyncio.sleep(_HEALTH_POLL_S)
        raise DBTStartupError(
            f"dbt-docs subprocess did not become healthy within {_HEALTH_TIMEOUT_S}s",
        )

    async def health(self) -> bool:
        """Return True if the dbt-docs root currently answers 200."""
        if not self.proc or self.proc.returncode is not None:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"http://127.0.0.1:{self.settings.docs_port}/",
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def stop(self) -> None:
        """Gracefully stop the dbt-docs subprocess.

        Sends SIGTERM, waits up to :data:`_SHUTDOWN_GRACE_S` seconds
        for clean exit, then escalates to SIGKILL.  Removes the PID
        file on exit so a follow-up start does not see a stale entry.
        """
        if not self.proc:
            return
        if self.proc.returncode is None:
            try:
                self.proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.proc.wait(), timeout=_SHUTDOWN_GRACE_S)
            except TimeoutError:
                _logger.warning(
                    "dbt-docs subprocess (pid=%s) did not exit within %.1fs of SIGTERM; "
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
