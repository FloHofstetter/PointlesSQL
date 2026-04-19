"""Persist + replay native-editor notebook outputs and per-cell runs.

Phase 12.6 Sprint 60 — the third layer of the native notebook story.
Sprint 59 streams kernel iopub messages to the client ephemerally;
this package mirrors every such message into SQLite so reopening a
notebook after kernel restart (or a page reload) paints the previous
session's outputs without re-running any code.

Sprint 79 split the original 480-LOC ``notebook_outputs.py`` into:

* :mod:`.outputs` — append / load / clear / rename for the
  ``NotebookOutput`` table (with cross-table cleanup of
  ``NotebookCellRun`` + ``NotebookCellRunSource`` on file-level
  operations).
* :mod:`.cell_runs` — lifecycle (``upsert_cell_run``) and per-execute
  history (``record_cell_run_start`` / ``_finish``,
  ``list_cell_run_sources``) for ``NotebookCellRun`` and
  ``NotebookCellRunSource``.

This package re-exports the full public surface so the lone external
caller ``from pointlessql.services import notebook_outputs as
notebook_outputs_service`` in
[pointlessql/api/main.py:48](pointlessql/api/main.py#L48) keeps
working unchanged.
"""

from __future__ import annotations

from pointlessql.services.notebook_outputs.cell_runs import (
    list_cell_run_sources,
    record_cell_run_finish,
    record_cell_run_start,
    upsert_cell_run,
)
from pointlessql.services.notebook_outputs.outputs import (
    append_output,
    clear_cell,
    clear_path,
    clear_session,
    is_persistable,
    load_outputs_for_path,
    rename_path,
)

__all__ = [
    "append_output",
    "clear_cell",
    "clear_path",
    "clear_session",
    "is_persistable",
    "list_cell_run_sources",
    "load_outputs_for_path",
    "record_cell_run_finish",
    "record_cell_run_start",
    "rename_path",
    "upsert_cell_run",
]
