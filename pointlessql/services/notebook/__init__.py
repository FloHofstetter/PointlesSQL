"""Notebook subsystem: doc model + workspace tree + outputs + kernel sessions.

This package consolidates the four notebook-related service
modules that used to live as a mix of flat files and standalone
sub-packages at ``pointlessql/services/`` root:

* ``notebook_doc.py``      → ``notebook._doc`` (parse + save .py
  notebook documents).
* ``notebook_workspace.py`` → ``notebook._workspace`` (filesystem
  workspace tree).
* ``notebook_outputs/``    → ``notebook.outputs/`` (cell-output
  persistence + per-cell-run history).
* ``kernel_session/``      → ``notebook.kernel_session/``
  (per-(user, path) ipykernel subprocess lifecycle).

The two sub-sub-packages keep their own facade ``__init__.py`` so
their internal multi-module split (outputs/ has cell_runs +
outputs; kernel_session/ has messages + session + registry) stays
addressable.  This is the only 2-level nesting in the Phase A–C
reorg — it's load-bearing because the alternative is leaving half
the notebook subsystem flat.
"""

from __future__ import annotations

from pointlessql.services.notebook._doc import (
    NotebookCell,
    NotebookDocument,
    compute_content_hash,
    load_document,
    resolve_py_notebook_path,
    save_document,
)
from pointlessql.services.notebook._workspace import (
    create_empty_notebook,
    delete_notebook,
    list_workspace_tree,
    rename_notebook,
    resolve_notebook_target,
    resolve_upload_target,
)

__all__ = [
    "NotebookCell",
    "NotebookDocument",
    "compute_content_hash",
    "create_empty_notebook",
    "delete_notebook",
    "list_workspace_tree",
    "load_document",
    "rename_notebook",
    "resolve_notebook_target",
    "resolve_py_notebook_path",
    "save_document",
]
