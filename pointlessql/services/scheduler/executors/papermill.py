# pyright: reportUnusedFunction=false
"""``papermill`` job kind — executes ``.ipynb`` / ``.py`` notebooks.

This module is the largest executor by far because it carries every
helper the kind needs: notebook-path resolution (incl. repo-prefix
support), jupytext-to-ipynb conversion, the blocking papermill
invocation under a module-level env lock, and the bridge that
persists papermill outputs into ``notebook_outputs`` so the
editor's replay surface and a future "view job outputs" tab share
one renderer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

from pointlessql.config import get_settings
from pointlessql.exceptions import EngineError, ValidationError
from pointlessql.services.scheduler.executors._papermill_logic import (
    is_code_cell,
    papermill_error_message,
    papermill_input_temp_path,
    papermill_output_path,
    transform_output_frame,
    validate_papermill_config,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


# Papermill drives kernel subprocesses that inherit the parent's
# ``os.environ``. Concurrent executions would otherwise race on the
# ``POINTLESSQL_PRINCIPAL`` slot when set through ``os.environ``; this
# lock serialises the narrow window between "set env" and "spawn kernel"
# without blocking the rest of the scheduler loop. Cell execution itself
# runs outside the lock.
_papermill_env_lock = threading.Lock()


_PAPERMILL_INPUT_SUFFIXES = frozenset({".ipynb", ".py"})


_REPO_PREFIX = "repo:"
"""Prefix marking a repo-backed notebook path.

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
    from pointlessql.config import get_settings

    body = spec[len(_REPO_PREFIX) :]
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
        raise ValidationError(f"repo notebook spec relative path must not be absolute: {spec!r}")
    if candidate.suffix not in _PAPERMILL_INPUT_SUFFIXES:
        raise ValidationError(f"repo notebook spec must end in .ipynb or .py: {spec!r}")

    settings = get_settings()
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
        raise ValidationError(f"repo notebook spec {spec!r} escapes its clone directory") from exc
    if not resolved.is_file():
        raise ValidationError(f"repo notebook not found: {spec!r}")
    return resolved


def resolve_notebook_path(notebooks_dir: Path, notebook_path: str) -> Path:
    """Resolve *notebook_path* under *notebooks_dir*, rejecting traversal.

    Accepts both ``.ipynb`` and ``.py`` (jupytext percent format)
    inputs — the :func:`_papermill_executor` converts ``.py`` to a
    temporary ``.ipynb`` before papermill runs it, so callers
    upstream can pass either format transparently.

    when *notebook_path* starts with the
    :data:`_REPO_PREFIX` it is resolved against the workspace-repo
    clone dir instead of *notebooks_dir*.  Repo-backed notebooks
    are read-only; the resolver returns the absolute path but the
    notebook-write surface refuses spec strings carrying the
    prefix.

    Args:
        notebooks_dir: Absolute root directory the notebook must live under.
        notebook_path: Relative path supplied in the job config, or a
            ``repo:<workspace_id>:<slug>/<rel>.py`` spec for repo-backed
            notebooks.

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
                # papermill is untyped; pin the attrs to concrete types
                # before handing them to the typed message builder.
                ename: str = exc.ename
                evalue: str = exc.evalue
                raise EngineError(papermill_error_message(exc.exec_count, ename, evalue)) from exc
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
    """  # noqa: DOC503 — ValidationError re-raised from validate_papermill_config / resolve_notebook_path
    del uc_client  # kernel subprocess builds its own PQL client

    settings = get_settings()
    notebook_path, parameters, timeout_seconds = validate_papermill_config(
        config, settings.jupyter.execute_timeout_seconds
    )

    notebooks_dir = Path(settings.jupyter.notebooks_dir).resolve()
    input_path = resolve_notebook_path(notebooks_dir, notebook_path)
    runs_dir = Path(settings.jupyter.runs_dir).resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = papermill_output_path(runs_dir, job_run_id)

    # If the user scheduled a ``.py`` notebook (jupytext percent
    # format), convert it to a sibling ``.ipynb`` inside the runs
    # dir before papermill sees it.  Papermill itself stays
    # ``.ipynb``-only; the convert step is a cheap jupytext call.
    papermill_input = input_path
    converted_temp: Path | None = None
    if input_path.suffix == ".py":
        converted_temp = papermill_input_temp_path(runs_dir, job_run_id)
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

    # bridge papermill outputs into ``notebook_outputs``
    # so the editor's persisted-output replay AND a future "view job
    # outputs" tab share one renderer. ``kernel_session_id`` carries a
    # synthetic ``job:<run_id>`` prefix so the row never collides with
    # an interactive kernel session UUID.
    try:
        await asyncio.to_thread(
            _persist_papermill_outputs,
            output_path,
            notebook_path,
            job_run_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("papermill: output-bridge failed for run %d", job_run_id)


def _persist_papermill_outputs(
    output_ipynb: Path,
    notebook_path: str,
    job_run_id: int,
    *,
    factory: Any = None,
) -> None:
    """Parse the executed ``.ipynb`` and write outputs to ``notebook_outputs``.

    Idempotent — clears any existing rows for the synthetic
    ``kernel_session_id`` first, so a retry produces the same final
    state. Runs inside an :func:`asyncio.to_thread` worker because
    nbformat parsing + DB writes are both synchronous.

    Args:
        output_ipynb: Path to the papermill-executed ``.ipynb``.
        notebook_path: Relative source notebook path (the editor uses
            this as the ``file_path`` column on ``notebook_outputs``).
        job_run_id: Surfacing run identifier; the synthetic
            ``kernel_session_id`` is ``f"job:{job_run_id}"``.
        factory: Optional SQLAlchemy session factory. Defaults to the
            globally-initialised factory from ``pointlessql.db`` so
            production callers stay one-line; tests inject the
            app-state factory directly because they never bootstrap
            the global ``init_db`` path.
    """
    import json as _json

    import nbformat  # type: ignore[import-untyped]

    from pointlessql.services.notebook import _doc as _doc_module
    from pointlessql.services.notebook import outputs as _outputs

    if not output_ipynb.exists():
        return

    if factory is None:
        from pointlessql.db import get_session_factory

        factory = get_session_factory()
    session_id = f"job:{job_run_id}"

    # Clear any earlier rows for this synthetic session — retries land
    # in a clean slate.
    try:
        _outputs.clear_session(
            factory,
            file_path=notebook_path,
            kernel_session_id=session_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "papermill: failed to clear notebook_outputs for %s session %s",
            notebook_path,
            session_id,
        )

    notebook = nbformat.read(str(output_ipynb), as_version=4)
    cell_index = 0
    for raw_cell in notebook.cells:
        if not is_code_cell(raw_cell):
            cell_index += 1
            continue
        source = raw_cell.source or ""
        content_hash = _doc_module.compute_content_hash(source)
        outputs: list[Any] = getattr(raw_cell, "outputs", []) or []
        for output_index, out in enumerate(outputs):
            msg_type, content_payload, metadata = transform_output_frame(out)
            try:
                _outputs.append_output(
                    factory,
                    file_path=notebook_path,
                    content_hash=content_hash,
                    kernel_session_id=session_id,
                    output_index=output_index,
                    msg_type=msg_type,
                    content=content_payload,
                    metadata=metadata,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "papermill: append_output failed (run=%d, cell=%d, idx=%d)",
                    job_run_id,
                    cell_index,
                    output_index,
                )
        cell_index += 1

    # Tiny audit-trail breadcrumb so a SELECT against ``notebook_outputs``
    # can be cross-checked against the papermill artefact path.
    logger.info(
        "papermill: persisted outputs for run %d (path=%s) ⇒ session=%s payload=%s",
        job_run_id,
        notebook_path,
        session_id,
        _json.dumps({"cells": cell_index}),
    )


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
