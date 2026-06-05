"""Pure decision and shaping logic for the ``papermill`` executor.

The executor drives jupytext conversion, a blocking papermill kernel
run, and an nbformat-to-``notebook_outputs`` bridge — all I/O.  The
config validation, run-artefact path building, papermill error
rendering, and the per-output transform that feeds the bridge are
I/O-free, so they live here for isolated unit testing.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pointlessql.exceptions import ValidationError


def validate_papermill_config(
    config: dict[str, Any],
    default_timeout_seconds: int,
) -> tuple[str, dict[str, Any], int]:
    """Validate a papermill job config and resolve its effective timeout.

    Args:
        config: The executor's job-config dict.
        default_timeout_seconds: Fallback per-cell timeout used when the
            config omits ``timeout_seconds``.

    Returns:
        A ``(notebook_path, parameters, timeout_seconds)`` triple.

    Raises:
        ValidationError: When ``notebook_path`` is absent or not a
            string, ``parameters`` is present but not an object, or
            ``timeout_seconds`` is present but not a positive int.
    """
    notebook_path = config.get("notebook_path")
    if not isinstance(notebook_path, str):
        raise ValidationError("papermill job config is missing required key 'notebook_path'")

    parameters = config.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValidationError("papermill job config 'parameters' must be an object")

    timeout_cfg = config.get("timeout_seconds")
    if timeout_cfg is None:
        timeout_seconds = default_timeout_seconds
    elif isinstance(timeout_cfg, int) and timeout_cfg > 0:
        timeout_seconds = timeout_cfg
    else:
        raise ValidationError("papermill job config 'timeout_seconds' must be a positive int")

    return notebook_path, parameters, timeout_seconds


def papermill_output_path(runs_dir: Path, job_run_id: int) -> Path:
    """Return the path the executed notebook is written to.

    Args:
        runs_dir: The configured runs directory.
        job_run_id: The current run id (used as the filename stem).

    Returns:
        ``{runs_dir}/{job_run_id}.ipynb``.
    """
    return runs_dir / f"{job_run_id}.ipynb"


def papermill_input_temp_path(runs_dir: Path, job_run_id: int) -> Path:
    """Return the temp ``.ipynb`` a ``.py`` notebook is converted into.

    Args:
        runs_dir: The configured runs directory.
        job_run_id: The current run id (used as the filename stem).

    Returns:
        ``{runs_dir}/{job_run_id}.input.ipynb``.
    """
    return runs_dir / f"{job_run_id}.input.ipynb"


def papermill_error_message(exec_count: Any, ename: str, evalue: str) -> str:
    """Render the engine-error message for a failed papermill cell.

    Args:
        exec_count: The 1-based execution count of the failing cell.
        ename: The exception class name from the kernel.
        evalue: The exception value/message from the kernel.

    Returns:
        A single-line message naming the cell and the exception.
    """
    return f"papermill execution failed in cell {exec_count}: {ename}: {evalue}"


def is_code_cell(cell: Any) -> bool:
    """Return whether *cell* is an executable code cell.

    Args:
        cell: An nbformat cell (or anything with a ``cell_type``
            attribute; missing attributes default to ``"code"``).

    Returns:
        ``True`` for code cells, ``False`` for markdown/raw cells.
    """
    return getattr(cell, "cell_type", "code") == "code"


def transform_output_frame(
    raw_output: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    """Split an nbformat output dict into the persisted load-shape.

    An nbformat output already carries the iopub message shape
    (``data``/``metadata`` for results, ``text`` for streams,
    ``ename``/``evalue``/``traceback`` for errors).  This separates the
    ``output_type`` discriminator, lifts ``metadata`` out of the
    content payload, and normalises a non-dict metadata to ``None``.

    Args:
        raw_output: One entry from a cell's ``outputs`` list.

    Returns:
        A ``(msg_type, content, metadata)`` triple — ``content`` is the
        output dict minus ``output_type`` and ``metadata``.
    """
    out_dict = dict(raw_output)
    msg_type = str(out_dict.get("output_type") or "execute_result")
    content = {k: v for k, v in out_dict.items() if k != "output_type"}
    metadata = content.pop("metadata", None)
    return msg_type, content, (metadata if isinstance(metadata, dict) else None)
