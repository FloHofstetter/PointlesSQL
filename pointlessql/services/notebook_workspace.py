"""Filesystem-facing helpers for the workspace browser.

The Papermill executor already owns
:func:`pointlessql.services.scheduler.resolve_notebook_path`, which
resolves a relative path under ``Settings.notebooks_dir`` and rejects
traversal. This module is the complementary surface for *browsing*,
*uploading*, and *mutating* notebooks in the workspace:

* :func:`list_workspace_tree` walks the notebooks directory and
  returns a nested tree the frontend renders as a sidebar. Each
  notebook leaf carries a ``parameters_tagged`` flag so the UI can
  hint which files will render a typed form in the create-job modal.
* :func:`resolve_notebook_target` validates a relative path under
  the notebooks directory and returns the resolved absolute path.
  Both accepted suffixes (``.py`` jupytext + ``.ipynb``) share the
  same traversal + parent-directory guard.
* :func:`resolve_upload_target` / :func:`create_empty_notebook` /
  :func:`rename_notebook` / :func:`delete_notebook` are thin callers
  over ``resolve_notebook_target`` that add the per-action side
  effect and the appropriate ``must_exist`` flag.

The top-level ``runs/`` subdirectory (executor output) is excluded
from the tree because its contents are synthetic sidecars keyed by
``job_run_id`` rather than user-authored sources. Dot-prefixed
directories at any depth (most visibly ``.ipynb_checkpoints/``
that Jupyter writes alongside every edited notebook) are filtered
out as well — they're storage artefacts, not user content.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from pointlessql.exceptions import ValidationError

logger = logging.getLogger(__name__)


_RUNS_DIR_NAME = "runs"
_SCRATCH_DIR_NAME = "scratch"
_NOTEBOOK_SUFFIX = ".ipynb"
_PY_NOTEBOOK_SUFFIX = ".py"
_NOTEBOOK_SUFFIXES = frozenset({_NOTEBOOK_SUFFIX, _PY_NOTEBOOK_SUFFIX})
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
            entry.is_file()
            and entry.suffix in _NOTEBOOK_SUFFIXES
            and not entry.name.startswith(".")
        ):
            # ``.py`` jupytext notebooks are first-class citizens in
            # the workspace tree; the frontend routes "Open in
            # editor" clicks based on the ``format`` marker.
            # ``parameters_tagged`` remains .ipynb-only because
            # papermill's inspect_notebook can't read .py directly —
            # the jupytext-convert step handles the .py path at
            # execute time, not at inspect time.
            notebook_format = "py" if entry.suffix == _PY_NOTEBOOK_SUFFIX else "ipynb"
            notebooks.append(
                {
                    "name": entry.name,
                    "path": str(entry.relative_to(notebooks_root)),
                    "kind": "notebook",
                    "format": notebook_format,
                    "parameters_tagged": (
                        _is_parameters_tagged(entry) if notebook_format == "ipynb" else False
                    ),
                }
            )

    return dirs + notebooks


def list_workspace_tree(notebooks_dir: Path) -> list[dict[str, Any]]:
    """Return a nested directory listing of ``notebooks_dir``.

    Top-level ``runs/`` (Papermill executor output) and ``scratch/``
    (Open-in-notebook output) are skipped because they hold
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


def resolve_notebook_target(
    notebooks_dir: Path,
    relative_path: str,
    *,
    allowed_suffixes: frozenset[str] = _NOTEBOOK_SUFFIXES,
) -> Path:
    """Validate a notebook path relative to ``notebooks_dir``.

    Shared by every mutation helper in this module: upload, create,
    rename, delete. Each caller layers its own pre-existence / post-
    existence check on top; this function owns only the traversal +
    parent-directory + suffix guards that every caller needs.

    Args:
        notebooks_dir: Absolute root the target must live under.
        relative_path: Relative path supplied by the API caller.
        allowed_suffixes: Allowed file suffixes. Defaults to both
            ``.py`` (jupytext Percent) and ``.ipynb``; upload keeps
            ``.ipynb`` only via :func:`resolve_upload_target`.

    Returns:
        Resolved absolute path. Pre- or post-existence is the caller's
        concern.

    Raises:
        ValidationError: On empty / absolute / wrong-suffix /
            traversal-escaping paths, or when the parent directory
            does not yet exist.
    """
    if not relative_path:
        raise ValidationError("notebook path must be a non-empty string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"notebook path must be relative to the notebooks directory: {relative_path!r}"
        )
    if candidate.suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise ValidationError(
            f"notebook path suffix must be one of {{{allowed}}}: {relative_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"notebook path {relative_path!r} escapes the notebooks directory"
        ) from exc
    parent = resolved.parent
    if not parent.is_dir():
        raise ValidationError(f"notebook path parent directory does not exist: {relative_path!r}")
    return resolved


def resolve_upload_target(notebooks_dir: Path, relative_path: str) -> Path:
    """Validate a notebook upload target and return its absolute path.

    Mirrors :func:`pointlessql.services.scheduler.resolve_notebook_path`
    but relaxes the "file must exist" constraint — the target file is
    about to be written, so pre-existence is the *opposite* of what we
    want. Keeps the ``.ipynb``-only suffix guard the original upload
    contract committed to; the create/rename/delete helpers use the
    relaxed :func:`resolve_notebook_target`.

    Args:
        notebooks_dir: Absolute root directory the target must live
            under.
        relative_path: Relative path supplied in the upload form.

    Returns:
        The resolved absolute path to the target ``.ipynb`` file. The
        file itself may or may not exist yet; the caller decides
        whether pre-existence is an error.  The ``ValidationError``
        contract of :func:`resolve_notebook_target` applies verbatim
        — empty / absolute / wrong-suffix / traversal / missing-
        parent paths all raise.
    """
    return resolve_notebook_target(
        notebooks_dir,
        relative_path,
        allowed_suffixes=frozenset({_NOTEBOOK_SUFFIX}),
    )


def create_empty_notebook(notebooks_dir: Path, relative_path: str) -> Path:
    """Write an empty ``.py`` jupytext notebook atomically.

    Backs the sidebar "New…" action. An empty file on disk is enough —
    the editor's open path already renders one empty cell and
    materialises cell markers on the first save when it encounters a
    zero-byte notebook. We still write the file eagerly so the tree
    refresh that fires after POST sees it before the user lands in the
    editor.

    Args:
        notebooks_dir: Absolute notebooks root.
        relative_path: Target relative path ending in ``.py``.

    Returns:
        The resolved absolute path of the newly created file.

    Raises:
        ValidationError: On any of the shared resolver guards, or
            when the file already exists (``409``-ish — surfaced as
            422 for parity with the upload route's overwrite guard).
    """
    resolved = resolve_notebook_target(
        notebooks_dir,
        relative_path,
        allowed_suffixes=frozenset({_PY_NOTEBOOK_SUFFIX}),
    )
    if resolved.exists():
        raise ValidationError(f"notebook already exists at {relative_path!r}")
    tmp_path = resolved.with_suffix(resolved.suffix + ".tmp")
    tmp_path.write_bytes(b"")
    os.replace(tmp_path, resolved)
    return resolved


def rename_notebook(
    notebooks_dir: Path,
    old_relative: str,
    new_relative: str,
) -> tuple[Path, Path]:
    """Atomically move an existing notebook to a new relative path.

    Backs the sidebar rename action. Both paths must live under
    ``notebooks_dir``; the source must exist, the destination must
    not. The suffix is unrestricted (``.py`` ↔ ``.py`` and
    ``.ipynb`` ↔ ``.ipynb`` are the realistic cases; cross-suffix
    renames are still allowed because the shared resolver does not
    distinguish). Output/run rows are *not* migrated here —
    :func:`pointlessql.services.notebook_outputs.rename_path` owns
    that side of the rename.

    Args:
        notebooks_dir: Absolute notebooks root.
        old_relative: Current relative path.
        new_relative: Target relative path.

    Returns:
        ``(old_resolved, new_resolved)`` — the resolved absolute paths
        before and after the move, for audit logging.

    Raises:
        ValidationError: On traversal escapes, bad suffix, missing
            source, or existing destination.
    """
    old_resolved = resolve_notebook_target(notebooks_dir, old_relative)
    new_resolved = resolve_notebook_target(notebooks_dir, new_relative)
    if not old_resolved.is_file():
        raise ValidationError(f"notebook to rename does not exist: {old_relative!r}")
    if new_resolved.exists():
        raise ValidationError(f"rename target already exists: {new_relative!r}")
    os.replace(old_resolved, new_resolved)
    return old_resolved, new_resolved


def delete_notebook(notebooks_dir: Path, relative_path: str) -> Path:
    """Delete a notebook file from the workspace.

    Backs the sidebar delete action. The output-row cascade is the
    caller's responsibility — the API route calls
    :func:`pointlessql.services.notebook_outputs.clear_path` right
    after ``delete_notebook`` returns so the two side effects stay
    explicit at the call site.

    Args:
        notebooks_dir: Absolute notebooks root.
        relative_path: Target relative path.

    Returns:
        The resolved absolute path that was removed (useful for
        audit logging).

    Raises:
        ValidationError: On traversal / suffix violations, or when
            the file does not exist.
    """
    resolved = resolve_notebook_target(notebooks_dir, relative_path)
    if not resolved.is_file():
        raise ValidationError(f"notebook to delete does not exist: {relative_path!r}")
    resolved.unlink()
    return resolved
