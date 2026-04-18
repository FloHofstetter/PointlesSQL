"""Filesystem-facing helpers for the Sprint 27 workspace browser.

The Papermill executor already owns
:func:`pointlessql.services.scheduler.resolve_notebook_path`, which
resolves a relative path under ``Settings.notebooks_dir`` and rejects
traversal. This module is the complementary surface for *browsing*
and *uploading* notebooks:

* :func:`list_workspace_tree` walks the notebooks directory and
  returns a nested tree the frontend renders as a sidebar. Each
  notebook leaf carries a ``parameters_tagged`` flag so the UI can
  hint which files will render a typed form in the create-job modal.
* :func:`resolve_upload_target` mirrors ``resolve_notebook_path`` but
  relaxes the "file must exist" check — uploads write a fresh path
  that does *not* yet exist on disk.

The top-level ``runs/`` subdirectory (executor output) is excluded
from the tree because its contents are synthetic sidecars keyed by
``job_run_id`` rather than user-authored sources. Dot-prefixed
directories at any depth (most visibly ``.ipynb_checkpoints/``
that Jupyter writes alongside every edited notebook) are filtered
out as well — they're storage artefacts, not user content.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pointlessql.exceptions import ValidationError

logger = logging.getLogger(__name__)


_RUNS_DIR_NAME = "runs"
_SCRATCH_DIR_NAME = "scratch"
_NOTEBOOK_SUFFIX = ".ipynb"
_SKIP_TOP_LEVEL_DIRS = frozenset({_RUNS_DIR_NAME, _SCRATCH_DIR_NAME})


def _is_parameters_tagged(notebook_path: Path) -> bool:
    """Return True when the notebook has a ``parameters``-tagged cell.

    Papermill's ``inspect_notebook`` returns an empty dict when no
    cell carries the ``parameters`` tag; a non-empty dict means at
    least one tagged cell exists. Inspection failures (malformed
    JSON, missing file race) are swallowed and reported as
    ``False`` so a single broken notebook does not 500 the whole
    tree listing.

    Args:
        notebook_path: Absolute path to an ``.ipynb`` file.

    Returns:
        True when Papermill finds at least one ``parameters``-tagged
        cell; False when the cell is absent or the file cannot be
        inspected.
    """
    import papermill  # type: ignore[import-untyped]

    try:
        raw = papermill.inspect_notebook(str(notebook_path))
    except Exception:  # noqa: BLE001 — papermill raises varied errors; inspect is best-effort UI hint
        logger.warning(
            "failed to inspect notebook %s; reporting parameters_tagged=False",
            notebook_path,
            exc_info=True,
        )
        return False
    return bool(raw)


def _walk(directory: Path, notebooks_root: Path) -> list[dict[str, Any]]:
    """Recursively build a tree rooted at *directory*.

    Args:
        directory: Absolute path being listed.
        notebooks_root: Absolute notebooks-dir root; used to compute
            the relative ``path`` field each tree node exposes.

    Returns:
        A list of directory and notebook nodes. Directories precede
        notebooks; both groups are sorted case-insensitively by name.
    """
    dirs: list[dict[str, Any]] = []
    notebooks: list[dict[str, Any]] = []

    for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            if directory == notebooks_root and entry.name in _SKIP_TOP_LEVEL_DIRS:
                continue
            if entry.name.startswith("."):
                continue
            dirs.append(
                {
                    "name": entry.name,
                    "path": str(entry.relative_to(notebooks_root)),
                    "kind": "dir",
                    "children": _walk(entry, notebooks_root),
                }
            )
        elif (
            entry.is_file() and entry.suffix == _NOTEBOOK_SUFFIX and not entry.name.startswith(".")
        ):
            notebooks.append(
                {
                    "name": entry.name,
                    "path": str(entry.relative_to(notebooks_root)),
                    "kind": "notebook",
                    "parameters_tagged": _is_parameters_tagged(entry),
                }
            )

    return dirs + notebooks


def list_workspace_tree(notebooks_dir: Path) -> list[dict[str, Any]]:
    """Return a nested directory listing of ``notebooks_dir``.

    Top-level ``runs/`` (Papermill executor output) and ``scratch/``
    (Sprint-34 Open-in-notebook output) are skipped because they hold
    machine-generated notebooks, not user-authored ones.

    Args:
        notebooks_dir: Absolute path to the notebooks root.

    Returns:
        A list of nodes. Each node is a dict with ``name``, ``path``
        (relative to ``notebooks_dir``), and ``kind`` in
        ``{"dir", "notebook"}``. Notebook nodes additionally carry
        ``parameters_tagged: bool``; directory nodes carry
        ``children: list[dict]``. Returns ``[]`` when the directory
        does not exist yet.
    """
    root = notebooks_dir
    if not root.is_dir():
        return []
    return _walk(root, root)


def resolve_upload_target(notebooks_dir: Path, relative_path: str) -> Path:
    """Validate a notebook upload target and return its absolute path.

    Mirrors :func:`pointlessql.services.scheduler.resolve_notebook_path`
    but relaxes the "file must exist" constraint — the target file is
    about to be written, so pre-existence is the *opposite* of what we
    want. The parent directory must already exist to prevent an
    uploader from creating arbitrary nested folders as a side effect.

    Args:
        notebooks_dir: Absolute root directory the target must live
            under.
        relative_path: Relative path supplied in the upload form.

    Returns:
        The resolved absolute path to the target ``.ipynb`` file. The
        file itself may or may not exist yet; the caller decides
        whether pre-existence is an error.

    Raises:
        ValidationError: When ``relative_path`` is empty, absolute,
            does not end in ``.ipynb``, escapes ``notebooks_dir``, or
            when its parent directory does not exist.
    """
    if not relative_path:
        raise ValidationError("notebook upload target_path must be a non-empty string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"notebook upload target_path must be relative to the "
            f"notebooks directory: {relative_path!r}"
        )
    if candidate.suffix != _NOTEBOOK_SUFFIX:
        raise ValidationError(
            f"notebook upload target_path must end in {_NOTEBOOK_SUFFIX!r}: {relative_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"notebook upload target_path {relative_path!r} escapes the notebooks directory"
        ) from exc
    parent = resolved.parent
    if not parent.is_dir():
        raise ValidationError(
            f"notebook upload target_path parent directory does not exist: {relative_path!r}"
        )
    return resolved
