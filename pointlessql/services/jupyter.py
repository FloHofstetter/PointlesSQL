"""Manage a JupyterLab subprocess alongside the FastAPI server."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from pointlessql.settings import Settings

_log = logging.getLogger(__name__)

_HEALTH_POLL_INTERVAL = 0.5
_HEALTH_POLL_TIMEOUT = 30.0
_SHUTDOWN_TIMEOUT = 5


@asynccontextmanager
async def managed_jupyter(
    settings: Settings,
) -> AsyncIterator[asyncio.subprocess.Process | None]:
    """Start JupyterLab as a subprocess and yield the process handle.

    Yields ``None`` immediately when *jupyter_enabled* is ``False``.
    On context exit the subprocess receives SIGTERM; if it does not
    exit within *_SHUTDOWN_TIMEOUT* seconds it is killed.
    """
    if not settings.jupyter_enabled:
        _log.info("Jupyter integration disabled — skipping subprocess start")
        yield None
        return

    notebook_dir = Path.cwd() / "notebooks"
    notebook_dir.mkdir(exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "jupyterlab",
        "--no-browser",
        f"--port={settings.jupyter_port}",
        "--ServerApp.token=''",
        "--ServerApp.password=''",
        "--ServerApp.disable_check_xsrf=True",
        "--ServerApp.allow_origin='*'",
        "--ServerApp.tornado_settings={'headers': {'Content-Security-Policy': \"frame-ancestors 'self' http://localhost:8000 http://127.0.0.1:8000\", 'X-Frame-Options': ''}}",
        f"--notebook-dir={notebook_dir}",
    ]

    _log.info("Starting JupyterLab on port %d …", settings.jupyter_port)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    await _wait_until_ready(settings.jupyter_port)

    try:
        yield proc
    finally:
        await _shutdown(proc)


async def _wait_until_ready(port: int) -> None:
    """Poll the JupyterLab HTTP endpoint until it responds or we time out."""
    url = f"http://localhost:{port}/lab"
    elapsed = 0.0
    async with httpx.AsyncClient() as client:
        while elapsed < _HEALTH_POLL_TIMEOUT:
            try:
                resp = await client.get(url, timeout=2.0)
                if resp.status_code < 500:
                    _log.info("JupyterLab ready on port %d", port)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(_HEALTH_POLL_INTERVAL)
            elapsed += _HEALTH_POLL_INTERVAL

    _log.warning(
        "JupyterLab did not become ready within %.0f s — "
        "the notebook iframe may fail to load",
        _HEALTH_POLL_TIMEOUT,
    )


async def _shutdown(proc: asyncio.subprocess.Process) -> None:
    """Gracefully terminate the JupyterLab subprocess."""
    if proc.returncode is not None:
        _log.info("JupyterLab already exited (rc=%d)", proc.returncode)
        return

    _log.info("Stopping JupyterLab (pid %d) …", proc.pid)
    proc.send_signal(signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_TIMEOUT)
        _log.info("JupyterLab stopped gracefully")
    except TimeoutError:
        _log.warning("JupyterLab did not exit in %d s — sending SIGKILL", _SHUTDOWN_TIMEOUT)
        proc.kill()
        await proc.wait()
