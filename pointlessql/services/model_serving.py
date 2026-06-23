"""Model-serving manager — registry models behind local REST workers.

Endpoint rows live in the metadata DB
(:class:`pointlessql.models.serving.ServingEndpoint`); this module
owns their runtime: one ``mlflow models serve`` subprocess per
started endpoint, bound to a loopback port from a configured range,
health-polled on spawn and torn down with the app.  The pattern
follows :mod:`pointlessql.services.mlflow_subprocess` (managed
long-running HTTP child), but multiplied by N endpoints and without
PID files — serving workers are deliberately process-scoped, so an
app restart resets every endpoint to ``stopped``.

The route layer proxies ``POST .../invocations`` to the worker's
``/invocations`` (the MLflow scoring protocol: ``dataframe_split`` /
``dataframe_records`` / ``instances``), so PointlesSQL's auth,
audit, and rate limits front every scoring request.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

from pointlessql.models.serving import ServingEndpoint

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.config import Settings

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_HEALTH_POLL_S = 0.5


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def validate_endpoint_name(name: str) -> str:
    """Return *name* stripped, or raise on a malformed identifier.

    Args:
        name: Candidate endpoint name (lands in the invocation URL).

    Returns:
        The stripped name.

    Raises:
        ValueError: When the name is empty, too long, or uses
            characters outside ``[A-Za-z0-9_-]``.
    """
    candidate = name.strip()
    if not _NAME_RE.match(candidate):
        raise ValueError(f"endpoint name must be 1-128 chars from [A-Za-z0-9_-], got {name!r}")
    return candidate


# ---------------------------------------------------------------------------
# DB CRUD
# ---------------------------------------------------------------------------


def create_endpoint(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    model_name: str,
    model_version: str,
    principal: str | None,
) -> ServingEndpoint:
    """Create an endpoint row in ``stopped`` state.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        name: Endpoint identifier (validated).
        model_name: Registry model name.
        model_version: Version string, or ``@alias``.
        principal: Creator e-mail.

    Returns:
        The persisted row (detached).

    Raises:
        ValueError: On a malformed name, empty model reference, or a
            name already taken in the workspace.
    """
    endpoint_name = validate_endpoint_name(name)
    if not model_name.strip() or not model_version.strip():
        raise ValueError("model_name and model_version must be non-empty")
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(ServingEndpoint).where(
                ServingEndpoint.workspace_id == workspace_id,
                ServingEndpoint.name == endpoint_name,
            )
        )
        if existing is not None:
            raise ValueError(f"serving endpoint {endpoint_name!r} already exists")
        row = ServingEndpoint(
            workspace_id=workspace_id,
            name=endpoint_name,
            model_name=model_name.strip(),
            model_version=model_version.strip(),
            created_by=principal,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_endpoints(factory: sessionmaker[Session], *, workspace_id: int) -> list[ServingEndpoint]:
    """List the workspace's endpoints ordered by name.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached endpoint rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(ServingEndpoint)
                .where(ServingEndpoint.workspace_id == workspace_id)
                .order_by(ServingEndpoint.name)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_endpoint(
    factory: sessionmaker[Session], *, workspace_id: int, name: str
) -> ServingEndpoint | None:
    """Return the workspace's endpoint by name, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        name: Endpoint identifier.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(ServingEndpoint).where(
                ServingEndpoint.workspace_id == workspace_id,
                ServingEndpoint.name == name,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def delete_endpoint(factory: sessionmaker[Session], *, endpoint_id: int) -> bool:
    """Delete an endpoint row.

    Args:
        factory: SQLAlchemy session factory.
        endpoint_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(ServingEndpoint, endpoint_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def set_state(
    factory: sessionmaker[Session],
    *,
    endpoint_id: int,
    state: str,
    error: str | None = None,
) -> None:
    """Persist a lifecycle transition.

    Args:
        factory: SQLAlchemy session factory.
        endpoint_id: Primary key.
        state: New state (caller passes a member of
            ``SERVING_ENDPOINT_STATES``).
        error: Failure detail recorded on ``failed`` transitions and
            cleared otherwise.
    """
    with factory() as session:
        row = session.get(ServingEndpoint, endpoint_id)
        if row is None:
            return
        row.state = state
        row.last_error = error
        row.updated_at = _utcnow()
        session.commit()


def record_invocation(factory: sessionmaker[Session], *, endpoint_id: int) -> None:
    """Bump the invocation counter (best-effort).

    Args:
        factory: SQLAlchemy session factory.
        endpoint_id: Primary key.
    """
    with factory() as session:
        row = session.get(ServingEndpoint, endpoint_id)
        if row is None:
            return
        row.invocation_count = int(row.invocation_count or 0) + 1
        row.last_invoked_at = _utcnow()
        session.commit()


def reset_states_on_boot(factory: sessionmaker[Session]) -> int:
    """Reset every non-``stopped`` endpoint to ``stopped``.

    Workers never outlive the app process, so stale ``ready`` /
    ``starting`` rows from the previous run are lies; the lifespan
    calls this once before serving traffic.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        Number of rows reset.
    """
    reset = 0
    with factory() as session:
        rows = session.scalars(select(ServingEndpoint).where(ServingEndpoint.state != "stopped"))
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
class ServingWorker:
    """One live scoring subprocess."""

    endpoint_id: int
    port: int
    process: Any
    stderr_path: Path


class ServingManager:
    """Process-global registry of live serving workers.

    One instance hangs off ``app.state.serving_manager`` (created
    lazily by :func:`get_serving_manager`); the lifespan tears it
    down via :meth:`stop_all`.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._workers: dict[int, ServingWorker] = {}
        self._lock = asyncio.Lock()

    def port_for(self, endpoint_id: int) -> int | None:
        """Return the live worker's port, or ``None`` when stopped."""
        worker = self._workers.get(endpoint_id)
        return worker.port if worker is not None else None

    def _allocate_port(self) -> int:
        """Pick the first free port in the configured range.

        Returns:
            A loopback port not used by any live worker.

        Raises:
            RuntimeError: When ``max_endpoints`` workers already run.
        """
        start = self._settings.serving.port_range_start
        used = {worker.port for worker in self._workers.values()}
        for offset in range(self._settings.serving.max_endpoints):
            candidate = start + offset
            if candidate not in used:
                return candidate
        raise RuntimeError(f"all {self._settings.serving.max_endpoints} serving slots are in use")

    def _build_command(self, model_uri: str, port: int) -> list[str]:
        """Compose the ``mlflow models serve`` argv."""
        return [
            sys.executable,
            "-m",
            "mlflow",
            "models",
            "serve",
            "-m",
            model_uri,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--env-manager",
            "local",
        ]

    async def _spawn(self, command: list[str], env: dict[str, str], stderr_path: Path) -> Any:
        """Start the worker subprocess (separated for test stubbing)."""
        stderr_file = stderr_path.open("wb")
        try:
            return await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=stderr_file,
                env=env,
            )
        finally:
            stderr_file.close()

    async def _wait_healthy(self, port: int, process: Any) -> None:
        """Poll the scoring server's ``/ping`` until healthy.

        Args:
            port: Worker port.
            process: The subprocess handle (early exit is failure).

        Raises:
            RuntimeError: When the worker exits early or the timeout
                elapses before ``/ping`` answers 200.
        """
        deadline = asyncio.get_event_loop().time() + (
            self._settings.serving.startup_timeout_seconds
        )
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                if process.returncode is not None:
                    raise RuntimeError(f"worker exited with code {process.returncode}")
                try:
                    response = await client.get(f"http://127.0.0.1:{port}/ping", timeout=2.0)
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(_HEALTH_POLL_S)
        raise RuntimeError("worker did not become healthy before the startup timeout")

    async def start(self, endpoint: ServingEndpoint) -> int:
        """Start a worker for *endpoint* and return its port.

        Args:
            endpoint: The (detached) endpoint row to serve.

        Returns:
            The worker's loopback port.

        Raises:
            RuntimeError: When no slot is free, the spawn fails, or
                the worker never becomes healthy (stderr tail
                included in the message).
        """
        async with self._lock:
            existing = self._workers.get(endpoint.id)
            if existing is not None:
                return existing.port
            port = self._allocate_port()
            version = endpoint.model_version
            model_uri = (
                f"models:/{endpoint.model_name}{version}"
                if version.startswith("@")
                else f"models:/{endpoint.model_name}/{version}"
            )
            env = os.environ.copy()
            env["MLFLOW_TRACKING_URI"] = f"http://127.0.0.1:{self._settings.mlflow.port}"
            stderr_path = Path(tempfile.gettempdir()) / f"pql-serving-{endpoint.id}.log"
            command = self._build_command(model_uri, port)
            process = await self._spawn(command, env, stderr_path)
            worker = ServingWorker(
                endpoint_id=endpoint.id,
                port=port,
                process=process,
                stderr_path=stderr_path,
            )
            self._workers[endpoint.id] = worker
        try:
            await self._wait_healthy(port, process)
        except RuntimeError as exc:
            await self.stop(endpoint.id)
            tail = _tail(stderr_path)
            detail = f"{exc}" + (f" — stderr tail: {tail}" if tail else "")
            raise RuntimeError(detail) from exc
        return port

    async def stop(self, endpoint_id: int) -> bool:
        """Stop and forget the endpoint's worker.

        Args:
            endpoint_id: Endpoint primary key.

        Returns:
            ``True`` when a worker was running.
        """
        async with self._lock:
            worker = self._workers.pop(endpoint_id, None)
        if worker is None:
            return False
        process = worker.process
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                logger.warning(
                    "model-serving worker did not exit within 5s of SIGTERM; killing",
                    extra={"endpoint_id": endpoint_id, "pid": process.pid},
                )
                process.kill()
                await process.wait()
        return True

    async def stop_all(self) -> None:
        """Tear down every live worker (lifespan shutdown)."""
        for endpoint_id in list(self._workers):
            await self.stop(endpoint_id)


def _tail(path: Path, *, max_bytes: int = 2000) -> str:
    """Return the last ``max_bytes`` of *path* as text (best-effort)."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-max_bytes:].decode("utf-8", errors="replace").strip()


def get_serving_manager(app: Any) -> ServingManager:
    """Return the app's serving manager, creating it on first use.

    Args:
        app: The FastAPI app (for ``app.state``).

    Returns:
        The process-global :class:`ServingManager`.
    """
    manager: ServingManager | None = getattr(app.state, "serving_manager", None)
    if manager is None:
        manager = ServingManager(app.state.settings)
        app.state.serving_manager = manager
    return manager
