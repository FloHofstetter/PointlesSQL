"""Async ``git`` subprocess helper.

Encapsulates the parts of :mod:`asyncio.subprocess` that are easy
to get subtly wrong: stdin pinning to ``/dev/null``,
``GIT_TERMINAL_PROMPT=0`` to keep git from blocking on a TTY when
auth fails, captured-stream draining inside the timeout, and a
hard kill escalation when the timeout trips.

The helper returns a :class:`GitRunResult` rather than raising on
non-zero exit — that decision is up to the calling provider
(``check_auth`` wants the diagnostic text either way; ``clone`` /
``pull`` want a hard error).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

GIT_BIN = shutil.which("git") or "git"
"""Resolved path to the ``git`` binary.

Falls back to the bare name when ``which`` returns nothing — that
keeps tests runnable in stripped containers where the binary is
``git`` on ``PATH`` but the resolution is unreliable.  Production
deploys should rely on the Dockerfile installing git explicitly
.
"""

STDOUT_TAIL_BYTES = 4 * 1024
"""How much stdout to keep for audit attachment (last N bytes)."""

STDERR_TAIL_BYTES = 4 * 1024
"""How much stderr to keep on failure for diagnostic surfaces."""


@dataclass(slots=True)
class GitRunResult:
    """Outcome of one ``git`` subprocess invocation.

    Attributes:
        returncode: ``git`` exit code.  ``0`` on success.
        stdout: Captured stdout (decoded UTF-8, last
            :data:`STDOUT_TAIL_BYTES` bytes).
        stderr: Captured stderr (decoded UTF-8, last
            :data:`STDERR_TAIL_BYTES` bytes).
        timed_out: ``True`` when the timeout tripped before the
            process exited cleanly.
    """

    returncode: int
    stdout: str = field(default="")
    stderr: str = field(default="")
    timed_out: bool = False


def _build_env(extra: dict[str, str] | None) -> dict[str, str]:
    """Return a clean env with the always-on git overrides."""
    env = os.environ.copy()
    # Never block on a credential prompt — we run in a daemon, not a TTY.
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Stable, predictable output that does not depend on the operator's locale.
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    if extra:
        env.update(extra)
    return env


def _tail(buf: bytes, limit: int) -> str:
    """Decode the last *limit* bytes of *buf* as UTF-8 (lossy)."""
    if len(buf) <= limit:
        return buf.decode("utf-8", errors="replace")
    return "...(truncated)\n" + buf[-limit:].decode("utf-8", errors="replace")


async def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 120.0,
) -> GitRunResult:
    """Run ``git`` with *args* and return a structured result.

    The helper never raises for non-zero exit codes — callers
    inspect :attr:`GitRunResult.returncode` and decide whether to
    raise a domain-specific error.  It does raise for the
    pre-spawn problems (binary missing, cwd missing) so those
    surface early as plain :class:`FileNotFoundError`.

    Args:
        args: Argument vector *after* ``git`` (e.g.
            ``["clone", "--branch", "main", "<url>", "<dir>"]``).
        cwd: Working directory for the subprocess.  ``None``
            inherits the process CWD.
        env: Extra env vars merged on top of the always-on
            overrides (``GIT_TERMINAL_PROMPT=0`` etc.).
        timeout_seconds: Hard deadline.  When the timeout trips
            the helper escalates SIGTERM → SIGKILL and returns
            :class:`GitRunResult` with ``timed_out=True``.

    Returns:
        :class:`GitRunResult` describing the outcome.

    Raises:
        FileNotFoundError: ``git`` binary missing or *cwd* does
            not exist.
    """
    if cwd is not None and not cwd.exists():
        raise FileNotFoundError(f"cwd does not exist: {cwd!s}")

    full_env = _build_env(env)
    logger.debug("running git %s (cwd=%s, timeout=%.1fs)", " ".join(args), cwd, timeout_seconds)

    proc = await asyncio.create_subprocess_exec(
        GIT_BIN,
        *args,
        cwd=str(cwd) if cwd is not None else None,
        env=full_env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("git timed out after %.1fs; killing pid=%s", timeout_seconds, proc.pid)
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        # Drain anything that's already buffered so we still surface a hint.
        try:
            stdout_b, stderr_b = await proc.communicate()
        except Exception:  # noqa: BLE001
            # bare-broad-ok: best-effort drain after kill; the timeout
            # log above already captured the failure context.
            stdout_b, stderr_b = b"", b""
        return GitRunResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=_tail(stdout_b, STDOUT_TAIL_BYTES),
            stderr=_tail(stderr_b, STDERR_TAIL_BYTES),
            timed_out=True,
        )

    return GitRunResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=_tail(stdout_b, STDOUT_TAIL_BYTES),
        stderr=_tail(stderr_b, STDERR_TAIL_BYTES),
        timed_out=False,
    )
