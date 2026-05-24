"""Cold-init seed loaders — build the initial Y.Doc payload from disk + DB."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import select

from pointlessql.models import Notebook
from pointlessql.models.notebook import NotebookCellIdentity
from pointlessql.services.notebook._doc import (
    load_document,
    resolve_py_notebook_path,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from pointlessql.config import Settings

_LOG = logging.getLogger(__name__)


def extract_seed_cells(
    document: Any,
    cell_uuid_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the ``seed_cells`` payload for :func:`get_or_init_ydoc`.

    The Y.Doc's :class:`pycrdt.Map` keys live for the duration of
    the live session; the canonical mapping is to the stable
    :class:`NotebookCellIdentity` row.  Cells with no live identity
    row (brand-new notebook never saved since Phase 95 landed) get a
    transient uuid4 so the doc is still navigable; the next save
    materialises a stable id and Sprint 105.5's save-barrier will
    broadcast a remap.

    Args:
        document: The :class:`NotebookDocument` returned by
            :func:`load_document`.
        cell_uuid_map: ``content_hash -> cell_uuid`` mapping resolved
            from ``notebook_cells`` (live rows only).

    Returns:
        Ordered list of ``{cell_uuid, source}`` dicts ready for
        :func:`_seed_cells_into_doc`.
    """
    seed: list[dict[str, Any]] = []
    for cell in document.cells:
        resolved = cell_uuid_map.get(cell.content_hash) or uuid4().hex
        seed.append({"cell_uuid": resolved, "source": cell.source})
    return seed


def build_seed(
    factory: sessionmaker[Any],
    settings: Settings,
    *,
    notebook_id: str,
) -> list[dict[str, Any]]:
    """Load a notebook's on-disk cells + resolve their stable UUIDs.

    Returns an empty list when the underlying ``.py`` file is missing
    (notebook row exists but file was renamed / deleted) — cold-init
    then produces an empty Doc, which is still a valid starting point
    for new collaborators.

    Args:
        factory: SQLAlchemy session factory from app state.
        settings: Application settings carrying ``jupyter.notebooks_dir``.
        notebook_id: 36-char :class:`Notebook` UUID.

    Returns:
        ``seed_cells`` payload for :func:`coedit_service.get_or_init_ydoc`.
    """
    with factory() as session:
        notebook = session.get(Notebook, notebook_id)
        if notebook is None:
            return []
        file_path = notebook.file_path
        rows = session.execute(
            select(
                NotebookCellIdentity.id,
                NotebookCellIdentity.current_content_hash,
            ).where(
                NotebookCellIdentity.notebook_id == notebook_id,
                NotebookCellIdentity.removed_at.is_(None),
            )
        ).all()
        cell_uuid_map: dict[str, str] = {row[1]: row[0] for row in rows}
    try:
        notebooks_dir = settings.jupyter.notebooks_dir.resolve()
        absolute = resolve_py_notebook_path(notebooks_dir, file_path, must_exist=True)
        document = load_document(absolute, file_path)
    except Exception:  # noqa: BLE001 — best-effort cold seed
        _LOG.exception(
            "coedit: cold-seed load failed for %s; starting with empty doc",
            notebook_id,
        )
        return []
    return extract_seed_cells(document, cell_uuid_map)
