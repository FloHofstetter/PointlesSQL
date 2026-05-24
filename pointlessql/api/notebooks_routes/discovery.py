"""Read-only discovery endpoints: tree listing + papermill inspect."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.notebook import _workspace as notebook_workspace_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/inspect")
async def api_inspect_notebook(request: Request, path: str) -> list[dict[str, Any]]:
    """Return a notebook's declared Papermill parameters.

    Introspects the ``parameters``-tagged cell via
    :func:`papermill.inspect_notebook` and returns one entry per
    declared parameter. The create-job modal and the in-editor
    Schedule + Run-Once modals use this to render a typed
    form instead of the raw JSON textarea.

    Papermill's introspector only accepts ``.ipynb`` JSON; ``.py``
    jupytext-Percent notebooks (PointlesSQL's canonical on-disk
    format ) get a transient conversion through a
    :class:`tempfile.NamedTemporaryFile` before the call so the
    caller never sees the difference.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative notebook path, resolved under
            :attr:`Settings.notebooks_dir`. Must not escape the
            directory — uses the same validator as the executor.

    Returns:
        A list of ``{"name", "default", "inferred_type", "help"}``
        dicts. ``default`` is the literal default string Papermill
        extracts (the client coerces it per ``inferred_type``).
    """
    import tempfile

    import jupytext  # type: ignore[import-untyped]
    import nbformat  # type: ignore[import-untyped]
    import papermill  # type: ignore[import-untyped]

    require_user(request)
    settings: Settings = request.app.state.settings
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        path,
    )
    if resolved.suffix == ".py":
        notebook = jupytext.read(resolved, fmt="py:percent")
        # Papermill's introspector reads the kernelspec to render
        # Jinja default-rewrites. Our jupytext-converted .py never
        # carries one (kernel selection is run-time via the WS layer),
        # so we stamp the canonical ``python3`` kernel here. Same
        # name :func:`_run_papermill_blocking` passes to execute.
        notebook.metadata.setdefault("kernelspec", {})
        notebook.metadata["kernelspec"].setdefault("name", "python3")
        notebook.metadata["kernelspec"].setdefault("display_name", "Python 3")
        notebook.metadata["kernelspec"].setdefault("language", "python")
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as fh:
            converted_path = fh.name
        try:
            nbformat.write(notebook, converted_path)
            raw = papermill.inspect_notebook(converted_path)
        finally:
            from pathlib import Path as _Path

            try:
                _Path(converted_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("inspect: failed to delete temp %s", converted_path)
    else:
        raw = papermill.inspect_notebook(str(resolved))
    out: list[dict[str, Any]] = []
    for name, meta in raw.items():
        meta_dict: dict[str, Any] = meta
        out.append(
            {
                "name": name,
                "default": meta_dict.get("default"),
                "inferred_type": meta_dict.get("inferred_type_name") or "str",
                "help": meta_dict.get("help", ""),
            },
        )
    return out


@router.get("/api/notebooks/tree")
async def api_notebooks_tree(request: Request) -> list[dict[str, Any]]:
    """Return a nested listing of the notebooks workspace directory.

    Admin-only, matching the inspect route. Each notebook leaf carries
    a ``parameters_tagged`` flag so the workspace UI can hint which
    files will render a typed form in the create-job modal.

    Args:
        request: Incoming FastAPI request; any authenticated user.

    Returns:
        A list of directory and notebook nodes. See
        :func:`pointlessql.services.notebook._workspace.list_workspace_tree`
        for the shape of each node.
    """
    require_user(request)
    settings: Settings = request.app.state.settings
    return notebook_workspace_service.list_workspace_tree(settings.jupyter.notebooks_dir.resolve())
