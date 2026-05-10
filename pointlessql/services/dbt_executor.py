"""On-demand ``dbt`` CLI subprocess wrapper.

Sibling to :mod:`pointlessql.services.dbt_subprocess`, which manages
the long-running ``dbt docs serve`` subprocess.  This module instead
spawns short-lived one-shot CLI invocations (``dbt run``, ``dbt test``,
``dbt compile``, ``dbt deps``) and waits for them to exit.

The executor returns a :class:`DBTRunResult` capturing exit code,
stdout, stderr, and the parsed paths to ``target/manifest.json`` and
``target/run_results.json``.  The bridge layer in
:mod:`pointlessql.services.dbt_bridge` then reads those files and
emits ``agent_run_operations`` rows.

We deliberately do not stream stdout to the HTTP response: dbt's
output is verbose, multi-second, and occasionally interleaves
multiple thread-prefixed lines that confuse log scrapers.  The
finished stdout/stderr bytes ride back in the JSON response so
callers can render them after the fact.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from pointlessql.config import DBTSettings
from pointlessql.exceptions import PointlessSQLError
from pointlessql.types import ErrorCode

_logger = logging.getLogger(__name__)


class DBTExecutionError(PointlessSQLError, RuntimeError):
    """Raised when a dbt CLI invocation cannot be spawned at all.

    Differentiates from a non-zero exit code, which is captured on
    :class:`DBTRunResult.exit_code` and lets the caller surface a
    structured result instead of an exception.

    Dual-parents :class:`PointlessSQLError` (centralised handler
    renders it as 503) and :class:`RuntimeError` (legacy ``except
    RuntimeError`` keeps catching).

    Attributes:
        status_code: Always 503 — the dbt CLI is part of the
            request path; an inability to spawn it is operational
            unavailability, not a client error.
        error_code: Always ``ErrorCode.DBT_EXECUTION_ERROR``.
    """

    status_code: int = 503
    error_code: ErrorCode = ErrorCode.DBT_EXECUTION_ERROR


@dataclass
class DBTRunResult:
    """Outcome of a single ``dbt`` CLI invocation.

    Attributes:
        command: Argv list actually spawned (``["dbt", "run", ...]``).
        exit_code: Process exit code; 0 for success, non-zero for
            partial-or-total failure.  ``dbt`` uses 1 for any model
            failure and 2 for fatal errors (compile failures, etc.).
        stdout: Captured stdout bytes decoded as UTF-8.  Truncated
            to :data:`_MAX_OUTPUT_BYTES` per stream so multi-MB
            payloads do not blow up the response.
        stderr: Captured stderr bytes decoded as UTF-8, same cap.
        manifest_path: Where dbt wrote the manifest after the run
            (``project_dir/target/manifest.json``).  Always set even
            on failure since dbt writes the manifest before any
            model executes.
        run_results_path: Where dbt wrote the per-node results
            (``project_dir/target/run_results.json``).  Always set
            but the file is only present when ``dbt`` reached the
            results-emit phase — compile failures skip it.
        duration_seconds: Wall-clock time the subprocess ran.
        truncated_stdout: True when ``stdout`` was clipped at
            :data:`_MAX_OUTPUT_BYTES`.
        truncated_stderr: True when ``stderr`` was clipped at
            :data:`_MAX_OUTPUT_BYTES`.
    """

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    manifest_path: Path
    run_results_path: Path
    duration_seconds: float = 0.0
    truncated_stdout: bool = field(default=False)
    truncated_stderr: bool = field(default=False)


_MAX_OUTPUT_BYTES = 256 * 1024  # 256 KiB per stream


def _truncate(buf: bytes) -> tuple[str, bool]:
    """Decode and truncate a captured stdout/stderr byte buffer.

    Args:
        buf: Raw bytes captured from the subprocess.

    Returns:
        tuple[str, bool]: The decoded string and a flag set when the
            input exceeded :data:`_MAX_OUTPUT_BYTES` bytes.  We
            decode with ``errors="replace"`` because dbt output is
            usually UTF-8 but can contain invalid bytes when a model
            includes binary debug data.
    """
    if len(buf) <= _MAX_OUTPUT_BYTES:
        return buf.decode("utf-8", errors="replace"), False
    head = buf[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return head + "\n... [truncated]", True


class DBTExecutor:
    """Run dbt CLI commands against a project, returning structured results.

    Args:
        settings: dbt configuration (project_dir, profiles_dir, target,
            timeout_seconds).
        cwd: Working directory anchor for relative-path defaults;
            defaults to ``Path.cwd()``.  Tests override with a
            fixture project.
    """

    def __init__(
        self,
        settings: DBTSettings,
        cwd: Path | None = None,
    ) -> None:
        self.settings = settings
        self.cwd = (cwd or Path.cwd()).resolve()

    @property
    def project_dir(self) -> Path:
        """Resolved project directory."""
        p = self.settings.project_dir
        return p if p.is_absolute() else (self.cwd / p).resolve()

    @property
    def profiles_dir(self) -> Path:
        """Resolved profiles directory."""
        p = self.settings.profiles_dir
        return p if p.is_absolute() else (self.cwd / p).resolve()

    @property
    def manifest_path(self) -> Path:
        """``target/manifest.json`` relative to the project dir."""
        return self.project_dir / "target" / "manifest.json"

    @property
    def run_results_path(self) -> Path:
        """``target/run_results.json`` relative to the project dir."""
        return self.project_dir / "target" / "run_results.json"

    def _base_args(self) -> list[str]:
        """Argv prefix shared by every CLI invocation."""
        return [
            "dbt",
            "--no-use-colors",  # plain output for log scrapers
            "--no-anonymous-usage-stats",  # don't phone home from a server
        ]

    def _project_flags(self) -> list[str]:
        """``--project-dir`` / ``--profiles-dir`` / ``--target`` flags."""
        return [
            "--project-dir",
            str(self.project_dir),
            "--profiles-dir",
            str(self.profiles_dir),
            "--target",
            self.settings.target,
        ]

    async def _run(self, *args: str) -> DBTRunResult:
        """Spawn a dbt subcommand and capture its output.

        Args:
            *args: Subcommand + flags (e.g. ``"run", "--select", "foo"``).

        Returns:
            DBTRunResult: Exit code + truncated stdout/stderr +
                manifest/run_results paths.

        Raises:
            DBTExecutionError: If the subprocess could not be spawned
                at all (missing binary, OS error).  Non-zero exit
                codes are *not* exceptions — they are captured on
                :class:`DBTRunResult.exit_code`.
        """
        cmd = [*self._base_args(), *args, *self._project_flags()]
        loop = asyncio.get_event_loop()
        start = loop.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=os.environ.copy(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise DBTExecutionError(
                "dbt CLI not found.  Install with `pip install pointlessql[dbt]`.",
            ) from exc
        except OSError as exc:
            raise DBTExecutionError(f"failed to spawn dbt: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.settings.timeout_seconds,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise DBTExecutionError(
                f"dbt {args[0] if args else ''} exceeded {self.settings.timeout_seconds}s timeout",
            ) from None

        duration = loop.time() - start
        out_str, out_trunc = _truncate(stdout)
        err_str, err_trunc = _truncate(stderr)
        _logger.info(
            "dbt %s exited with code %d in %.2fs",
            args[0] if args else "?",
            proc.returncode or 0,
            duration,
        )
        return DBTRunResult(
            command=cmd,
            exit_code=proc.returncode or 0,
            stdout=out_str,
            stderr=err_str,
            manifest_path=self.manifest_path,
            run_results_path=self.run_results_path,
            duration_seconds=duration,
            truncated_stdout=out_trunc,
            truncated_stderr=err_trunc,
        )

    async def compile(self, models: list[str] | None = None) -> DBTRunResult:
        """Run ``dbt compile`` to refresh the manifest without writing data.

        Args:
            models: Optional ``--select`` filter list.

        Returns:
            DBTRunResult: Exit code + output + manifest path.
        """
        args: list[str] = ["compile"]
        if models:
            args += ["--select", " ".join(models)]
        return await self._run(*args)

    async def deps(self) -> DBTRunResult:
        """Run ``dbt deps`` to install packages declared in packages.yml.

        Required before ``run`` / ``test`` if the project depends on
        ``dbt-expectations`` or ``dbt-utils``.
        """
        return await self._run("deps")

    async def seed(self, models: list[str] | None = None) -> DBTRunResult:
        """Run ``dbt seed`` to materialise CSV seeds as duckdb tables.

        Models that ``ref()`` a seed (e.g. the sample project's
        ``bronze_raw`` referencing ``orders.csv``) need this to have
        run at least once before ``dbt run`` will succeed.

        Args:
            models: Optional ``--select`` filter list of seed names.

        Returns:
            DBTRunResult: Exit code + output; ``run_results.json``
                receives one entry per executed seed.
        """
        args: list[str] = ["seed"]
        if models:
            args += ["--select", " ".join(models)]
        return await self._run(*args)

    async def run(
        self,
        models: list[str] | None = None,
        full_refresh: bool = False,
    ) -> DBTRunResult:
        """Run ``dbt run`` to materialise models.

        Args:
            models: Optional ``--select`` filter list.
            full_refresh: When True, pass ``--full-refresh`` to drop +
                rebuild incremental tables instead of merging.

        Returns:
            DBTRunResult: Exit code + run_results.json path for the
                bridge to parse.
        """
        args: list[str] = ["run"]
        if models:
            args += ["--select", " ".join(models)]
        if full_refresh:
            args.append("--full-refresh")
        return await self._run(*args)

    async def test(self, models: list[str] | None = None) -> DBTRunResult:
        """Run ``dbt test`` to evaluate test definitions.

        Args:
            models: Optional ``--select`` filter list (e.g. ``["bronze"]``
                runs only tests on bronze models).

        Returns:
            DBTRunResult: Exit code + run_results.json path; per-test
                pass/fail rows live in run_results.json and are parsed
                by the bridge.
        """
        args: list[str] = ["test"]
        if models:
            args += ["--select", " ".join(models)]
        return await self._run(*args)
