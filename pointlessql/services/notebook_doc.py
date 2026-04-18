"""Load and save ``.py`` notebooks in jupytext's Percent format.

Phase 12.6 Sprint 58 — the first half of the native-notebook-editor
skeleton. This module is the single point of contact between the
on-disk ``.py`` notebook source of truth and the HTTP layer that
serves cells to Monaco on the client.

Three invariants, all derived from ADR 0001:

* **On-disk format is jupytext Percent.** Every cell boundary is a
  ``# %%`` marker (or one of the aliases jupytext parses: ``# ---``,
  ``# COMMAND ----------``, ``# In[N]:``). Write-path normalises to
  ``# %%`` unless the file header pins a different marker through a
  ``jupytext.cell_markers`` entry.
* **Cell identity travels in the marker.** Every cell carries a UUID
  written as ``# %% pql_cell_id="<uuid>"``; jupytext round-trips
  arbitrary cell metadata through the percent-format marker when
  the notebook-level ``jupytext.cell_metadata_filter`` allow-lists
  the key. Foreign notebooks without IDs are assigned fresh UUIDs
  on first load and the dirty state is reported back to the caller
  (one-time save prompt in the UI).
* **No execution state lives here.** Outputs, execution counts, and
  kernel sessions belong to Sprint 60's ``notebook_outputs`` table.
  This module deals with source text and cell metadata only.

The caller is expected to have already resolved the target path under
the notebooks directory via :func:`resolve_py_notebook_path`, which is
the ``.py`` sibling of :func:`notebook_workspace.resolve_upload_target`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jupytext  # type: ignore[import-untyped]
import nbformat  # type: ignore[import-untyped]

from pointlessql.exceptions import ValidationError

_PY_NOTEBOOK_SUFFIX = ".py"
_CELL_ID_KEY = "pql_cell_id"
_CELL_METADATA_FILTER = f"{_CELL_ID_KEY},-all"


@dataclass(frozen=True)
class NotebookCell:
    """A single notebook cell as served to the editor.

    Attributes:
        id: Stable UUID. Assigned on first save when a foreign ``.py``
            lacks an ``id=`` marker; round-tripped through jupytext
            cell metadata thereafter.
        cell_type: ``"code"`` or ``"markdown"``. Raw cells are not
            supported in the editor — they're rewritten to markdown on
            load (one-way, acceptable for Phase 12.6).
        source: Cell source text. Markdown cells carry raw markdown
            without comment-escaping; jupytext handles the
            ``# %% [markdown]`` round-trip.
    """

    id: str
    cell_type: str
    source: str


@dataclass(frozen=True)
class NotebookDocument:
    """A whole ``.py`` notebook as served to the editor.

    Attributes:
        path: Relative path under the notebooks directory.
        cells: Ordered list of cells.
        dirty: ``True`` when at least one cell gained a freshly
            generated UUID during load — the editor should prompt the
            user to save so the IDs are persisted to disk. Subsequent
            loads of the same file report ``False``.
    """

    path: str
    cells: list[NotebookCell]
    dirty: bool


def resolve_py_notebook_path(
    notebooks_dir: Path,
    relative_path: str,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve a ``.py`` notebook path under the notebooks directory.

    Mirrors :func:`notebook_workspace.resolve_upload_target` but for
    ``.py`` files rather than ``.ipynb``. The traversal guard is
    identical — the relative path must stay under ``notebooks_dir``
    after ``Path.resolve``.

    Args:
        notebooks_dir: Absolute notebooks root.
        relative_path: Caller-supplied relative path.
        must_exist: When ``True`` (the default), a missing file is an
            error — used on the load path. When ``False``, the file
            may be brand-new but its parent directory must already
            exist — used on the save path.

    Returns:
        Resolved absolute path.

    Raises:
        ValidationError: Empty / absolute / wrong-suffix / escaping
            path; or a missing file when ``must_exist`` is ``True``;
            or a missing parent when ``must_exist`` is ``False``.
    """
    if not relative_path:
        raise ValidationError("notebook path must be a non-empty string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"notebook path must be relative to the notebooks directory: {relative_path!r}"
        )
    if candidate.suffix != _PY_NOTEBOOK_SUFFIX:
        raise ValidationError(
            f"notebook path must end in {_PY_NOTEBOOK_SUFFIX!r}: {relative_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"notebook path {relative_path!r} escapes the notebooks directory"
        ) from exc
    if must_exist:
        if not resolved.is_file():
            raise ValidationError(f"notebook not found: {relative_path!r}")
    else:
        if not resolved.parent.is_dir():
            raise ValidationError(
                f"notebook parent directory does not exist: {relative_path!r}"
            )
    return resolved


def load_document(absolute_path: Path, relative_path: str) -> NotebookDocument:
    """Load a ``.py`` notebook off disk and assign missing cell IDs.

    Uses :func:`jupytext.read` to parse the Percent format; any
    marker variant jupytext recognises is accepted. Cells without an
    ``id`` in their jupytext metadata receive a freshly generated
    UUID and the document is flagged ``dirty`` so the caller can
    prompt a save.

    Args:
        absolute_path: Pre-resolved path produced by
            :func:`resolve_py_notebook_path`.
        relative_path: Relative path (as the caller supplied it) —
            stored on the returned document for the editor UI.

    Returns:
        A :class:`NotebookDocument` with ordered cells and the
        ``dirty`` flag set when at least one UUID was minted.
    """
    notebook = jupytext.read(absolute_path, fmt="py:percent")
    cells: list[NotebookCell] = []
    dirty = False
    for raw_cell in notebook.cells:
        cell_metadata: dict[str, Any] = getattr(raw_cell, "metadata", {}) or {}
        cell_id = cell_metadata.get(_CELL_ID_KEY)
        if not isinstance(cell_id, str) or not cell_id:
            cell_id = str(uuid.uuid4())
            cell_metadata[_CELL_ID_KEY] = cell_id
            raw_cell.metadata = cell_metadata
            dirty = True
        raw_type = getattr(raw_cell, "cell_type", "code")
        cell_type = "markdown" if raw_type == "markdown" else "code"
        cells.append(
            NotebookCell(
                id=cell_id,
                cell_type=cell_type,
                source=raw_cell.source or "",
            )
        )
    return NotebookDocument(path=relative_path, cells=cells, dirty=dirty)


def save_document(absolute_path: Path, cells: list[NotebookCell]) -> None:
    """Write cells back to disk in jupytext Percent format.

    The default cell marker is ``# %%``; jupytext also honours any
    per-file ``cell_markers`` pin in an existing frontmatter header.
    Cell IDs are written as ``id=<uuid>`` in the marker line so the
    round-trip is lossless.

    Args:
        absolute_path: Pre-resolved target path.
        cells: Ordered cells to write. Each must already carry a
            stable :attr:`NotebookCell.id` — fresh UUIDs are not
            minted here; use :func:`load_document`'s dirty flow for
            that.
    """
    nb_cells: list[Any] = []
    for cell in cells:
        if cell.cell_type == "markdown":
            nb_cell = nbformat.v4.new_markdown_cell(cell.source)
        else:
            nb_cell = nbformat.v4.new_code_cell(cell.source)
        nb_cell.metadata[_CELL_ID_KEY] = cell.id
        nb_cells.append(nb_cell)
    notebook = nbformat.v4.new_notebook(cells=nb_cells)
    notebook.metadata.setdefault("jupytext", {})["cell_metadata_filter"] = _CELL_METADATA_FILTER
    jupytext.write(notebook, absolute_path, fmt="py:percent")
