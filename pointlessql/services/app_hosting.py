"""Hosted data apps — small web apps as managed subprocesses.

App rows live in the metadata DB
(:class:`pointlessql.models.hosted_apps.HostedApp`); this module owns
their CRUD plus the runtime: one worker subprocess per started app
(uvicorn for ``kind="fastapi"``, streamlit for ``kind="streamlit"``,
an operator-supplied argv for ``kind="command"``), bound to a
loopback port from a configured range, health-polled on spawn and
torn down with the host process.  The pattern follows
:mod:`pointlessql.services.model_serving` (N managed long-running
HTTP children, no PID files) — workers are deliberately
process-scoped, so a host restart resets every app to ``stopped``.

The route layer fronts every browser request with an authenticating
reverse-proxy (:mod:`pointlessql.api.apps_proxy`), so the apps
themselves never need an auth surface of their own.
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import json
import logging
import os
import re
import shlex
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

from pointlessql.exceptions import PointlessSQLError
from pointlessql.models.hosted_apps import HOSTED_APP_KINDS, HostedApp

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_HEALTH_POLL_S = 0.5

_UNSET: Any = object()
"""Sentinel distinguishing "leave unchanged" from "set to None"."""


@dataclass(frozen=True)
class AppsConfig:
    """Runtime knobs for the hosted-apps worker pool.

    A plain frozen dataclass so the manager stays constructible
    without the full settings tree; the application wiring builds
    one from real settings and hands it to :class:`AppsManager`.

    Attributes:
        port_range_start: First loopback port handed to a worker.
        max_apps: Cap on concurrently-running workers (each is a
            full Python process).
        startup_timeout_seconds: Bound on the post-spawn health
            poll before the start is declared failed.
        request_timeout_seconds: Bound on a single proxied request
            to a worker.
        apps_root: Directory the app sources are materialised
            under; ``None`` falls back to
            ``<tempdir>/pql-apps``.
    """

    port_range_start: int = 9200
    max_apps: int = 8
    startup_timeout_seconds: float = 60.0
    request_timeout_seconds: float = 30.0
    apps_root: Path | None = field(default=None)


class AppRuntimeMissingError(PointlessSQLError, RuntimeError):
    """Raised when an app's runtime package is not importable.

    Dual-parents :class:`PointlessSQLError` (so the centralised
    handler renders it as 503) and :class:`RuntimeError` (so generic
    ``except RuntimeError`` clauses around worker startup continue
    to catch).

    Attributes:
        status_code: Always 503.
    """

    status_code: int = 503


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _slugify(title: str) -> str:
    """Derive a collision-proof slug from *title* (mirrors BI dashboards)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "app"
    return f"{base}-{uuid.uuid4().hex[:6]}"


@functools.cache
def streamlit_available() -> bool:
    """Return ``True`` if the optional ``streamlit`` package is importable.

    Cached because the spec lookup walks ``sys.path``; the answer
    cannot change within one process lifetime anyway.  Operators
    install streamlit themselves (``pip install streamlit``) — it is
    not a PointlesSQL dependency.

    Returns:
        bool: ``True`` when ``import streamlit`` would succeed.
    """
    import importlib.util

    return importlib.util.find_spec("streamlit") is not None


def stderr_log_path(app_id: int) -> Path:
    """Return the worker's stderr capture file for *app_id*.

    Deterministic so the log-tail route can find the file after the
    worker stopped (or crashed) without asking the manager.

    Args:
        app_id: App primary key.

    Returns:
        Path of the per-app stderr log under the system tempdir.
    """
    return Path(tempfile.gettempdir()) / f"pql-app-{app_id}.log"


def read_log_tail(app_id: int, *, max_lines: int = 200) -> list[str]:
    """Return the last *max_lines* lines of the app's stderr log.

    Args:
        app_id: App primary key.
        max_lines: Cap on returned lines (oldest dropped first).

    Returns:
        The trailing log lines; empty when no log exists yet.
    """
    path = stderr_log_path(app_id)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-max_lines:]


def _validate_kind_fields(kind: str, command_override: str | None) -> None:
    """Reject invalid kind / command combinations.

    Args:
        kind: Candidate runtime kind.
        command_override: Custom argv template (``kind="command"``).

    Raises:
        ValueError: When *kind* is unknown or a ``command`` app has
            no command line.
    """
    if kind not in HOSTED_APP_KINDS:
        raise ValueError(f"kind must be one of {', '.join(HOSTED_APP_KINDS)}; got {kind!r}")
    if kind == "command" and not (command_override or "").strip():
        raise ValueError("command apps need a command_override")


def _encode_env(env: dict[str, str] | None) -> str:
    """Serialise an env mapping to the stored JSON text.

    Args:
        env: Extra environment variables, or ``None`` for none.

    Returns:
        Canonical JSON object text (``"{}"`` for empty).

    Raises:
        ValueError: When a key or value is not a string.
    """
    if not env:
        return "{}"
    for key, value in env.items():
        # Deliberate defensive check — JSON-shaped callers reach this
        # seam with unvalidated payloads despite the annotation.
        if not isinstance(key, str) or not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("env must map string keys to string values")
    return json.dumps(env, sort_keys=True)


# ---------------------------------------------------------------------------
# DB CRUD
# ---------------------------------------------------------------------------


def create_app(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    title: str,
    description: str | None,
    kind: str,
    source_code: str,
    command_override: str | None,
    env: dict[str, str] | None,
    created_by_user_id: int,
) -> HostedApp:
    """Create an app row in ``stopped`` state.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        title: Human-readable name (slug derives from it).
        description: Optional free-form description.
        kind: Runtime kind (member of ``HOSTED_APP_KINDS``).
        source_code: Contents of the app's ``app.py``.
        command_override: Custom argv template (``kind="command"``).
        env: Extra environment variables (may carry secret
            references — stored verbatim).
        created_by_user_id: Creating user's id.

    Returns:
        The persisted row (detached).

    Raises:
        ValueError: On an empty title, unknown kind, a command app
            without a command line, or a non-string env mapping.
    """
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("title must be a non-empty string")
    _validate_kind_fields(kind, command_override)
    env_json = _encode_env(env)
    now = _utcnow()
    row = HostedApp(
        workspace_id=workspace_id,
        slug=_slugify(cleaned),
        title=cleaned,
        description=description,
        kind=kind,
        source_code=source_code,
        command_override=command_override,
        env_json=env_json,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_apps(factory: sessionmaker[Session], *, workspace_id: int) -> list[HostedApp]:
    """List the workspace's apps, newest-updated first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached app rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(HostedApp)
                .where(HostedApp.workspace_id == workspace_id)
                .order_by(HostedApp.updated_at.desc())
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_app(factory: sessionmaker[Session], *, workspace_id: int, slug: str) -> HostedApp | None:
    """Return the workspace's app by slug, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        slug: App slug.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(HostedApp).where(
                HostedApp.workspace_id == workspace_id,
                HostedApp.slug == slug,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def update_app(
    factory: sessionmaker[Session],
    *,
    app_id: int,
    title: str = _UNSET,
    description: str | None = _UNSET,
    source_code: str = _UNSET,
    command_override: str | None = _UNSET,
    env: dict[str, str] | None = _UNSET,
) -> HostedApp | None:
    """Patch the given fields of an app row.

    The slug never changes — it is the app's URL identity and the
    proxy path browsers may have bookmarked.

    Args:
        factory: SQLAlchemy session factory.
        app_id: Primary key.
        title: New title, when given.
        description: New description, when given.
        source_code: New ``app.py`` contents, when given (takes
            effect on the next start).
        command_override: New argv template, when given.
        env: New env mapping, when given.

    Returns:
        The refreshed detached row, or ``None`` when absent.

    Raises:
        ValueError: On an empty title, clearing the command line of
            a command app, or a non-string env mapping.
    """
    with factory() as session:
        row = session.get(HostedApp, app_id)
        if row is None:
            return None
        if title is not _UNSET:
            cleaned = title.strip()
            if not cleaned:
                raise ValueError("title must be a non-empty string")
            row.title = cleaned
        if description is not _UNSET:
            row.description = description
        if source_code is not _UNSET:
            row.source_code = source_code
        if command_override is not _UNSET:
            _validate_kind_fields(row.kind, command_override)
            row.command_override = command_override
        if env is not _UNSET:
            row.env_json = _encode_env(env)
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_app(factory: sessionmaker[Session], *, app_id: int) -> bool:
    """Delete an app row.

    Args:
        factory: SQLAlchemy session factory.
        app_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(HostedApp, app_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def set_state(
    factory: sessionmaker[Session],
    *,
    app_id: int,
    state: str,
    error: str | None = None,
) -> None:
    """Persist a lifecycle transition.

    Args:
        factory: SQLAlchemy session factory.
        app_id: Primary key.
        state: New state (caller passes a member of
            ``HOSTED_APP_STATES``).
        error: Failure detail recorded on ``failed`` transitions and
            cleared otherwise.
    """
    with factory() as session:
        row = session.get(HostedApp, app_id)
        if row is None:
            return
        row.state = state
        row.last_error = error
        row.updated_at = _utcnow()
        session.commit()


def reset_states_on_boot(factory: sessionmaker[Session]) -> int:
    """Reset every non-``stopped`` app to ``stopped``.

    Workers never outlive the host process, so stale ``ready`` /
    ``starting`` rows from the previous run are lies; the lifespan
    calls this once before serving traffic.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        Number of rows reset.
    """
    reset = 0
    with factory() as session:
        rows = session.scalars(select(HostedApp).where(HostedApp.state != "stopped"))
        for row in rows:
            row.state = "stopped"
            row.updated_at = _utcnow()
            reset += 1
        if reset:
            session.commit()
    return reset


# ---------------------------------------------------------------------------
# Worker manager
# ---------------------------------------------------------------------------


@dataclass
class AppWorker:
    """One live app subprocess."""

    app_id: int
    port: int
    process: Any
    stderr_path: Path


class AppsManager:
    """Process-global registry of live app workers.

    One instance hangs off ``app.state.apps_manager`` (created by
    the lifespan); routes obtain it from there and 503 when it is
    missing.  The lifespan tears it down via :meth:`stop_all`.
    """

    def __init__(self, config: AppsConfig) -> None:
        self.config = config
        self._workers: dict[int, AppWorker] = {}
        self._lock = asyncio.Lock()

    def port_for(self, app_id: int) -> int | None:
        """Return the live worker's port, or ``None`` when stopped."""
        worker = self._workers.get(app_id)
        return worker.port if worker is not None else None

    @property
    def apps_root(self) -> Path:
        """Directory app sources are materialised under."""
        if self.config.apps_root is not None:
            return self.config.apps_root
        return Path(tempfile.gettempdir()) / "pql-apps"

    def _allocate_port(self) -> int:
        """Pick the first free port in the configured range.

        Returns:
            A loopback port not used by any live worker.

        Raises:
            RuntimeError: When ``max_apps`` workers already run.
        """
        start = self.config.port_range_start
        used = {worker.port for worker in self._workers.values()}
        for offset in range(self.config.max_apps):
            candidate = start + offset
            if candidate not in used:
                return candidate
        raise RuntimeError(f"all {self.config.max_apps} app slots are in use")

    def _materialize(self, app: HostedApp) -> Path:
        """Write the app's source to its working directory.

        Re-written on every start so source edits take effect on the
        next restart without a separate deploy step.

        Args:
            app: The (detached) app row.

        Returns:
            The app's working directory (cwd for the worker).
        """
        app_dir = self.apps_root / str(app.workspace_id) / app.slug
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "app.py").write_text(app.source_code or "", encoding="utf-8")
        return app_dir

    def _build_command(self, app: HostedApp, port: int) -> list[str]:
        """Compose the worker argv for the app's kind.

        Args:
            app: The (detached) app row.
            port: Allocated loopback port.

        Returns:
            The argv to spawn.

        Raises:
            AppRuntimeMissingError: When a streamlit app is started
                but the ``streamlit`` package is not installed.
            ValueError: When a command app has an empty command
                line (defence; create/update validate it too).
        """
        if app.kind == "fastapi":
            return [
                sys.executable,
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        if app.kind == "streamlit":
            if not streamlit_available():
                raise AppRuntimeMissingError(
                    "streamlit is not installed — install it "
                    "(pip install streamlit) to run streamlit apps"
                )
            return [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.port",
                str(port),
                "--server.address",
                "127.0.0.1",
                "--server.headless",
                "true",
                "--server.baseUrlPath",
                f"/apps/{app.slug}",
            ]
        command = (app.command_override or "").strip()
        if not command:
            raise ValueError("command apps need a command_override")
        return [part.replace("{port}", str(port)) for part in shlex.split(command)]

    async def _spawn(
        self,
        command: list[str],
        env: dict[str, str],
        stderr_path: Path,
        cwd: Path,
    ) -> Any:
        """Start the worker subprocess (separated for test stubbing).

        Args:
            command: The argv to execute.
            env: Full environment for the child.
            stderr_path: File the child's stderr is captured to.
            cwd: Working directory (the materialised app dir).

        Returns:
            The asyncio subprocess handle.
        """
        stderr_file = stderr_path.open("wb")
        try:
            return await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=stderr_file,
                env=env,
                cwd=str(cwd),
            )
        finally:
            stderr_file.close()

    async def _wait_healthy(self, port: int, process: Any) -> None:
        """Poll the worker's HTTP root until it answers.

        Any status below 500 counts as healthy — a FastAPI app
        without a root route answers 404 and a streamlit worker
        redirects to its base path, both of which prove the server
        is up and routing.

        Args:
            port: Worker port.
            process: The subprocess handle (early exit is failure).

        Raises:
            RuntimeError: When the worker exits early or the timeout
                elapses before the root answers.
        """
        deadline = asyncio.get_event_loop().time() + self.config.startup_timeout_seconds
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                if process.returncode is not None:
                    raise RuntimeError(f"worker exited with code {process.returncode}")
                try:
                    response = await client.get(f"http://127.0.0.1:{port}/", timeout=2.0)
                    if response.status_code < 500:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(_HEALTH_POLL_S)
        raise RuntimeError("worker did not become healthy before the startup timeout")

    async def start(self, app: HostedApp, *, env: dict[str, str]) -> int:
        """Start a worker for *app* and return its port.

        The caller resolves secret references in *env* beforehand —
        the manager never touches the secrets store.  Composing the
        worker argv may also propagate
        :class:`AppRuntimeMissingError` when the app's runtime
        package (e.g. streamlit) is not installed.

        Args:
            app: The (detached) app row to serve.
            env: Extra environment variables (already resolved),
                merged over a copy of the host environment plus
                ``POINTLESSQL_APP_BASE_PATH`` and ``PORT``.

        Returns:
            The worker's loopback port.

        Raises:
            RuntimeError: When no slot is free, the spawn fails, or
                the worker never becomes healthy (stderr tail
                included in the message).
        """
        async with self._lock:
            existing = self._workers.get(app.id)
            if existing is not None:
                return existing.port
            port = self._allocate_port()
            command = self._build_command(app, port)
            app_dir = self._materialize(app)
            merged_env = os.environ.copy()
            merged_env.update({str(k): str(v) for k, v in env.items()})
            merged_env["POINTLESSQL_APP_BASE_PATH"] = f"/apps/{app.slug}"
            merged_env["PORT"] = str(port)
            stderr_path = stderr_log_path(app.id)
            process = await self._spawn(command, merged_env, stderr_path, app_dir)
            worker = AppWorker(
                app_id=app.id,
                port=port,
                process=process,
                stderr_path=stderr_path,
            )
            self._workers[app.id] = worker
        try:
            await self._wait_healthy(port, process)
        except RuntimeError as exc:
            await self.stop(app.id)
            tail = _tail(stderr_path)
            detail = f"{exc}" + (f" — stderr tail: {tail}" if tail else "")
            raise RuntimeError(detail) from exc
        return port

    async def stop(self, app_id: int) -> bool:
        """Stop and forget the app's worker.

        Args:
            app_id: App primary key.

        Returns:
            ``True`` when a worker was running.
        """
        async with self._lock:
            worker = self._workers.pop(app_id, None)
        if worker is None:
            return False
        process = worker.process
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                logger.warning(
                    "hosted-app worker did not exit within 5s of SIGTERM; killing",
                    extra={"app_id": app_id, "pid": process.pid},
                )
                process.kill()
                await process.wait()
        return True

    async def stop_all(self) -> None:
        """Tear down every live worker (lifespan shutdown)."""
        for app_id in list(self._workers):
            await self.stop(app_id)


def _tail(path: Path, *, max_bytes: int = 2000) -> str:
    """Return the last ``max_bytes`` of *path* as text (best-effort)."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-max_bytes:].decode("utf-8", errors="replace").strip()
