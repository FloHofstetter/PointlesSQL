# pyright: reportUnusedFunction=false
"""Built-in job executors (pg_sync, python, papermill, alert_check).

Every executor matches the
:data:`pointlessql.services.scheduler.registry.JobExecutor` signature
and is referenced from
:func:`pointlessql.services.scheduler.registry.build_default_registry`.

All cross-module imports inside executor bodies stay function-local
(``pg_sync``, ``alerts``, ``pql.pql``, ``authorization``) to dodge a
circular import chain through ``pointlessql.db`` and ``models``.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.metadata as _md
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import select

from pointlessql.config import Settings
from pointlessql.exceptions import EngineError, ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _pg_sync_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute the ``pg_sync`` kind by calling ``pg_sync.run_sync``.

    Resolves the catalog's connection and (optional) credential through
    the principal-forwarded ``uc_client`` so the scheduler inherits the
    same authorization path the manual "Sync now" route uses.

    Args:
        job_run_id: Current run id (unused here but part of the
            :data:`JobExecutor` signature).
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``catalog_name``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``catalog_name`` is missing from config
            or the catalog is not a foreign catalog.
    """
    del job_run_id, user_info  # unused but part of executor signature

    catalog_name = config.get("catalog_name")
    if not catalog_name:
        raise ValidationError("pg_sync job config is missing required key 'catalog_name'")

    from pointlessql.db import get_session_factory
    from pointlessql.services import pg_sync as pg_sync_service

    catalog = await uc_client.get_catalog(str(catalog_name))
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise ValidationError(f"pg_sync job target '{catalog_name}' is not a foreign catalog")
    connection = await uc_client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = options.get("credential_name") if isinstance(options, dict) else None
    if credential_name:
        credential = await uc_client.get_credential(str(credential_name))

    factory = get_session_factory()
    await pg_sync_service.run_sync(
        uc=uc_client,
        factory=factory,
        catalog_name=str(catalog_name),
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )


async def _python_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute a user-authored job published via a ``pointlessql.jobs`` entry point.

    The ``entry_point`` key in ``config`` selects the entry-point name;
    the loaded object must be a coroutine with the
    :data:`JobExecutor` signature. This keeps plug-in authorship simple:
    ship a wheel that declares

    .. code-block:: toml

        [project.entry-points."pointlessql.jobs"]
        my_job = "my_pkg.jobs:run_my_job"

    and PointlesSQL discovers it without further configuration.

    Args:
        job_run_id: Current run id, forwarded to the plug-in.
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``entry_point``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``entry_point`` is missing or the entry
            point resolution fails.
    """
    entry_point_name = config.get("entry_point")
    if not entry_point_name:
        raise ValidationError("python job config is missing required key 'entry_point'")

    try:
        entries = _md.entry_points(group="pointlessql.jobs")
    except TypeError:  # pragma: no cover — very old importlib.metadata
        entries = _md.entry_points().get("pointlessql.jobs", [])  # type: ignore[attr-defined]

    matches = [ep for ep in entries if ep.name == entry_point_name]
    if not matches:
        raise ValidationError(f"python job entry point not found: {entry_point_name!r}")

    fn = matches[0].load()
    await fn(job_run_id, user_info, config, uc_client)


# Papermill drives kernel subprocesses that inherit the parent's
# ``os.environ``. Concurrent executions would otherwise race on the
# ``POINTLESSQL_PRINCIPAL`` slot when set through ``os.environ``; this
# lock serialises the narrow window between "set env" and "spawn kernel"
# without blocking the rest of the scheduler loop. Cell execution itself
# runs outside the lock.
_papermill_env_lock = threading.Lock()


_PAPERMILL_INPUT_SUFFIXES = frozenset({".ipynb", ".py"})


_REPO_PREFIX = "repo:"
"""Prefix marking a repo-backed notebook path (Phase 51.3).

Format: ``repo:<workspace_id>:<slug>/<rel-path>.py``.  The
resolver maps this to
``<settings.workspace_repos.base_dir>/<workspace_id>/<slug>/<rel-path>.py``
and reads the file read-only.  Write attempts go through the
notebook-write path which checks for the prefix and refuses
(notebooks in repos are git-canonical; edits go via PR).
"""


def _resolve_repo_notebook_path(spec: str) -> Path:
    """Resolve a ``repo:<ws>:<slug>/<rel>.py`` spec to an absolute path.

    Args:
        spec: Notebook-path spec carrying the :data:`_REPO_PREFIX`.

    Returns:
        Absolute path inside the resolved clone dir.

    Raises:
        ValidationError: Spec format invalid, suffix unsupported,
            traversal attempted, or file missing on disk.
    """
    # Local import to avoid a top-level dependency on settings/git
    # for callers that never use the repo-prefix path.
    from pointlessql.config import Settings

    body = spec[len(_REPO_PREFIX):]
    # Split on the first slash to separate the "<workspace_id>:<slug>"
    # head from the relative path tail.
    if "/" not in body:
        raise ValidationError(
            f"repo notebook spec must be 'repo:<workspace_id>:<slug>/<path>': {spec!r}"
        )
    head, rel = body.split("/", 1)
    if ":" not in head:
        raise ValidationError(
            f"repo notebook spec must be 'repo:<workspace_id>:<slug>/<path>': {spec!r}"
        )
    workspace_id_str, slug = head.split(":", 1)
    if not workspace_id_str.isdigit() or not slug:
        raise ValidationError(
            f"repo notebook spec carries a non-numeric workspace_id or empty slug: {spec!r}"
        )
    if not rel:
        raise ValidationError(f"repo notebook spec is missing the relative path: {spec!r}")
    candidate = Path(rel)
    if candidate.is_absolute():
        raise ValidationError(
            f"repo notebook spec relative path must not be absolute: {spec!r}"
        )
    if candidate.suffix not in _PAPERMILL_INPUT_SUFFIXES:
        raise ValidationError(
            f"repo notebook spec must end in .ipynb or .py: {spec!r}"
        )

    settings = Settings()
    base_dir = settings.workspace_repos.base_dir
    clone_dir = (base_dir / workspace_id_str / slug).resolve()
    if not clone_dir.exists():
        raise ValidationError(
            f"repo clone directory does not exist; sync the repo first: {clone_dir!s}"
        )
    resolved = (clone_dir / candidate).resolve()
    try:
        resolved.relative_to(clone_dir)
    except ValueError as exc:
        raise ValidationError(
            f"repo notebook spec {spec!r} escapes its clone directory"
        ) from exc
    if not resolved.is_file():
        raise ValidationError(f"repo notebook not found: {spec!r}")
    return resolved


def resolve_notebook_path(notebooks_dir: Path, notebook_path: str) -> Path:
    """Resolve *notebook_path* under *notebooks_dir*, rejecting traversal.

    Accepts both ``.ipynb`` and ``.py`` (jupytext percent format)
    inputs — the :func:`_papermill_executor` converts ``.py`` to a
    temporary ``.ipynb`` before papermill runs it, so callers
    upstream can pass either format transparently.

    Phase 51.3 — when *notebook_path* starts with the
    :data:`_REPO_PREFIX` it is resolved against the workspace-repo
    clone dir instead of *notebooks_dir*.  Repo-backed notebooks
    are read-only; the resolver returns the absolute path but the
    notebook-write surface refuses spec strings carrying the
    prefix.

    Args:
        notebooks_dir: Absolute root directory the notebook must live under.
        notebook_path: Relative path supplied in the job config, or a
            ``repo:<workspace_id>:<slug>/<rel>.py`` spec for repo-backed
            notebooks (Phase 51.3).

    Returns:
        The resolved absolute path to the input notebook.

    Raises:
        ValidationError: When *notebook_path* is absolute, empty, has
            an unsupported suffix, escapes *notebooks_dir*, or does
            not point at an existing file.
    """
    if not notebook_path:
        raise ValidationError("papermill job config 'notebook_path' must be a non-empty string")
    if notebook_path.startswith(_REPO_PREFIX):
        return _resolve_repo_notebook_path(notebook_path)
    candidate = Path(notebook_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"papermill notebook_path must be relative to the notebooks "
            f"directory: {notebook_path!r}"
        )
    if candidate.suffix not in _PAPERMILL_INPUT_SUFFIXES:
        raise ValidationError(
            f"papermill notebook_path must end in .ipynb or .py: {notebook_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"papermill notebook_path {notebook_path!r} escapes the notebooks directory"
        ) from exc
    if not resolved.is_file():
        raise ValidationError(f"papermill notebook not found: {notebook_path!r}")
    return resolved


def _run_papermill_blocking(
    input_path: Path,
    output_path: Path,
    parameters: dict[str, Any],
    cwd: Path,
    principal: str,
    execution_timeout: int,
) -> None:
    """Invoke ``papermill.execute_notebook`` synchronously.

    Runs inside an ``asyncio.to_thread`` worker. Sets
    ``POINTLESSQL_PRINCIPAL`` on ``os.environ`` under a module-level
    lock so the spawned Jupyter kernel inherits the run-as user's
    email for :class:`~pointlessql.pql.PQL` to pick up.
    """
    import papermill  # type: ignore[import-untyped]
    from papermill.exceptions import (  # type: ignore[import-untyped]
        PapermillExecutionError,
    )

    with _papermill_env_lock:
        previous = os.environ.get("POINTLESSQL_PRINCIPAL")
        os.environ["POINTLESSQL_PRINCIPAL"] = principal
        try:
            try:
                papermill.execute_notebook(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    parameters=parameters,
                    kernel_name="python3",
                    cwd=str(cwd),
                    execution_timeout=execution_timeout,
                    progress_bar=False,
                )
            except PapermillExecutionError as exc:
                raise EngineError(
                    f"papermill execution failed in cell {exc.exec_count}: "
                    f"{exc.ename}: {exc.evalue}"
                ) from exc
        finally:
            if previous is None:
                os.environ.pop("POINTLESSQL_PRINCIPAL", None)
            else:
                os.environ["POINTLESSQL_PRINCIPAL"] = previous


async def _papermill_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute a notebook via Papermill, writing the result under ``runs/``.

    Config shape:

    .. code-block:: json

        {
            "notebook_path": "pipelines/etl.ipynb",
            "parameters": {"date": "2026-04-17"},
            "timeout_seconds": 600
        }

    ``notebook_path`` is resolved relative to ``settings.jupyter.notebooks_dir``
    and must not escape it. The executed output lands at
    ``{runs_dir}/{job_run_id}.ipynb`` (where ``runs_dir`` defaults to
    ``{notebooks_dir}/runs`` for backward compatibility).
    (the job-detail page links straight to that URL). ``timeout_seconds``
    is forwarded to papermill's per-cell ``execution_timeout`` and also
    backstopped by an ``asyncio.wait_for`` around the blocking call.

    The run-as user's email is exported as ``POINTLESSQL_PRINCIPAL`` in
    the Jupyter kernel subprocess so any :class:`~pointlessql.pql.PQL`
    instance constructed inside the notebook inherits the same
    principal forwarding the scheduler applies to its own
    ``uc_client``.

    Args:
        job_run_id: Current run id — used as the output filename.
        user_info: The run-as user's :class:`UserInfo` — ``email`` is
            exported as ``POINTLESSQL_PRINCIPAL`` for the kernel.
        config: Must carry ``notebook_path``. ``parameters`` and
            ``timeout_seconds`` are optional.
        uc_client: Principal-forwarded facade. Not used directly by the
            executor (notebook code constructs its own :class:`PQL`)
            but kept in the signature for symmetry with the other
            built-in kinds.

    Raises:
        ValidationError: When ``notebook_path`` is missing, not a
            string, escapes ``notebooks_dir``, or does not exist; or
            when ``parameters`` / ``timeout_seconds`` have the wrong
            type.
        EngineError: When the notebook raises during execution, when
            the execution exceeds the timeout, or when papermill
            itself errors out.
    """
    del uc_client  # kernel subprocess builds its own PQL client

    notebook_path = config.get("notebook_path")
    if not isinstance(notebook_path, str):
        raise ValidationError("papermill job config is missing required key 'notebook_path'")

    parameters = config.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValidationError("papermill job config 'parameters' must be an object")

    settings = Settings()
    timeout_cfg = config.get("timeout_seconds")
    if timeout_cfg is None:
        timeout_seconds = settings.jupyter.execute_timeout_seconds
    elif isinstance(timeout_cfg, int) and timeout_cfg > 0:
        timeout_seconds = timeout_cfg
    else:
        raise ValidationError("papermill job config 'timeout_seconds' must be a positive int")

    notebooks_dir = Path(settings.jupyter.notebooks_dir).resolve()
    input_path = resolve_notebook_path(notebooks_dir, notebook_path)
    runs_dir = Path(settings.jupyter.runs_dir).resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{job_run_id}.ipynb"

    # If the user scheduled a ``.py`` notebook (jupytext percent
    # format), convert it to a sibling ``.ipynb`` inside the runs
    # dir before papermill sees it.  Papermill itself stays
    # ``.ipynb``-only; the convert step is a cheap jupytext call.
    papermill_input = input_path
    converted_temp: Path | None = None
    if input_path.suffix == ".py":
        converted_temp = runs_dir / f"{job_run_id}.input.ipynb"
        await asyncio.to_thread(_jupytext_py_to_ipynb, input_path, converted_temp)
        papermill_input = converted_temp
        logger.info(
            "papermill: converted %s → %s before execute",
            input_path,
            converted_temp,
        )

    principal = user_info["email"]
    logger.info(
        "papermill: executing %s → %s (timeout=%ds, principal=%s)",
        papermill_input,
        output_path,
        timeout_seconds,
        principal,
    )

    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                _run_papermill_blocking,
                papermill_input,
                output_path,
                dict(parameters),
                notebooks_dir,
                principal,
                timeout_seconds,
            ),
            timeout=timeout_seconds + 5,
        )
    except TimeoutError as exc:
        raise EngineError(f"papermill execution timed out after {timeout_seconds}s") from exc
    finally:
        if converted_temp is not None and converted_temp.exists():
            try:
                converted_temp.unlink()
            except OSError:
                logger.warning("failed to delete jupytext-convert temp %s", converted_temp)
    logger.info("papermill: finished %s", output_path)


def _jupytext_py_to_ipynb(src: Path, dst: Path) -> None:
    """Convert a jupytext Percent ``.py`` to an ``.ipynb`` on disk.

    Runs inside an :func:`asyncio.to_thread` worker because jupytext's
    read + nbformat write are both synchronous.  Used by
    :func:`_papermill_executor` before handing the notebook to
    papermill, which only speaks ``.ipynb``.

    Args:
        src: Absolute path to the ``.py`` input.
        dst: Absolute path the converted ``.ipynb`` will land at.
    """
    import jupytext  # type: ignore[import-untyped]
    import nbformat  # type: ignore[import-untyped]

    notebook = jupytext.read(src, fmt="py:percent")
    nbformat.write(notebook, dst)


async def _alert_check_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Evaluate a query alert's condition and dispatch events.

    Config shape:

    .. code-block:: json

        {"alert_id": 42}

    Runs the alert's saved query via :class:`~pointlessql.pql.pql.PQL`
    under the owner's UC identity (the scheduler already threaded
    ``uc_client`` with the right principal).  On condition match it
    records one :class:`~pointlessql.models.AlertEvent` row, then fans
    out dispatch for every enabled destination.  Webhook delivery
    failures flip the event's ``outcome`` to ``delivery_failed``
    without raising — the alert check itself is considered successful
    as long as the condition was evaluated.

    Args:
        job_run_id: Current run id (unused; the alert's own
            ``AlertEvent`` row carries the history).
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``alert_id``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``alert_id`` is missing from config.
    """
    del job_run_id  # unused; the AlertEvent row carries the history
    alert_id = config.get("alert_id")
    if not isinstance(alert_id, int):
        raise ValidationError("alert_check job config missing integer 'alert_id'")

    from uuid import uuid4

    import duckdb

    from pointlessql.db import get_session_factory
    from pointlessql.models import Alert, AlertDestination, SavedQuery
    from pointlessql.pql.pql import PQL
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql
    from pointlessql.services import alerts as alerts_service
    from pointlessql.services.alert_dispatcher import dispatch_webhook
    from pointlessql.services.authorization import SELECT, check_privilege

    factory = get_session_factory()
    with factory() as session:
        alert = session.get(Alert, alert_id)
        if alert is None or not alert.is_active:
            return
        saved = session.get(SavedQuery, alert.saved_query_id)
        if saved is None:
            return
        sql_text = saved.sql_text
        alert_slug = alert.slug
        saved_query_slug = saved.slug
        condition_op = alert.condition_op
        threshold = alert.threshold

    try:
        prepared = prepare_sql(sql_text)
    except SQLParseError as exc:
        logger.warning("alert %s: SQL parse failed: %s", alert_slug, exc)
        return

    approved: dict[str, str] = {}
    for full_name in prepared.refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            logger.warning("alert %s: unexpected ref shape %r", alert_slug, full_name)
            return
        table_info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not table_info:
            logger.warning(
                "alert %s: referenced table %s not found",
                alert_slug,
                full_name,
            )
            return
        storage_location = table_info.get("storage_location")
        if not isinstance(storage_location, str) or not storage_location:
            logger.warning(
                "alert %s: table %s has no storage_location",
                alert_slug,
                full_name,
            )
            return
        await check_privilege(
            uc_client,
            user_info["email"],
            bool(user_info["is_admin"]),
            "table",
            full_name,
            SELECT,
        )
        approved[full_name] = storage_location

    conn = duckdb.connect()
    try:
        result = await asyncio.to_thread(
            PQL.sql,
            sql_text,
            approved_tables=approved,
            max_rows=100_000,
            conn=conn,
            explain=False,
        )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — diagnostic only
            logger.debug("alert %s: conn.close raised", alert_slug, exc_info=True)

    if not alerts_service.evaluate_condition(result.row_count, condition_op, threshold):
        return

    now = datetime.datetime.now(datetime.UTC)
    envelope = alerts_service.build_cloudevent(
        event_id=uuid4().hex,
        alert_slug=alert_slug,
        saved_query_slug=saved_query_slug,
        condition_op=condition_op,
        threshold=threshold,
        row_count=result.row_count,
        duration_ms=result.duration_ms,
        referenced_tables=result.referenced_tables,
        fired_at=now,
    )
    payload_json = json.dumps(envelope, sort_keys=True)
    alerts_service.record_event(
        factory,
        alert_id=alert_id,
        event_id=envelope["id"],
        fired_at=now,
        row_count=result.row_count,
        outcome="fired",
        payload_json=payload_json,
    )

    # Fan out webhook dispatches.
    with factory() as session:
        dests = list(
            session.scalars(
                select(AlertDestination).where(
                    AlertDestination.alert_id == alert_id,
                    AlertDestination.is_active.is_(True),
                )
            ).all()
        )
    delivery_failed = False
    for dest in dests:
        if dest.kind != "webhook" or not dest.webhook_url:
            continue
        ok = await dispatch_webhook(
            dest.webhook_url,
            envelope,
            hmac_secret=dest.hmac_secret,
        )
        if not ok:
            delivery_failed = True
    if delivery_failed:
        alerts_service.set_event_outcome(factory, envelope["id"], "delivery_failed")


async def _branch_cleanup_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run the  branch auto-cleanup pass.

    Walks UC schemas, picks ``status='active'`` branches past the
    configured retention, and discards them.  Default-disabled — the
    underlying :func:`cleanup_old_branches` short-circuits when
    ``settings.branch.auto_cleanup_enabled`` is false.

    Runs the sync helper inside :func:`asyncio.to_thread` so the
    sync ``discard_branch_schema`` (which itself emits CloudEvents
    via the running loop) doesn't fight the scheduler's loop with
    nested ``asyncio.run`` calls.

    Args:
        job_run_id: Current run id (unused; the cleanup writes its
            own audit-log rows per discard).
        user_info: Run-as user (unused; cleanup runs without a
            principal-scoped audit run).
        config: Reserved for future per-job overrides.  Currently
            unused — all knobs come from settings.
        uc_client: Principal-forwarded facade (we use the underlying
            client for its sync transport).
    """
    del job_run_id, user_info, config

    from pointlessql.services.branch_cleanup import cleanup_old_branches

    settings = Settings()
    summary = await asyncio.to_thread(
        cleanup_old_branches,
        client=uc_client._client,  # noqa: SLF001 — sync soyuz client  # pyright: ignore[reportPrivateUsage]
        settings=settings,
    )
    logger.info("branch_cleanup_executor: %s", summary)
