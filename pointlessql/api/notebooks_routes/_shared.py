"""Shared helpers across the ``notebooks_routes`` package.

Holds the template-resolver shim and the notebook-UUID lookup
that every sub-module reaches for.  Pulled out so the per-axis
route files stay focused on their own surface (discovery / crud
/ io / jobs / pages).
"""

from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models.notebook import Notebook

logger = logging.getLogger(__name__)


def templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def get_or_create_notebook_uuid(
    request: Request, file_path: str
) -> str:
    """Look up or create the :class:`Notebook` UUID for *file_path*.

    the social layer addresses notebooks by their
    stable ``notebooks.id`` UUID (locked decision #8).  This helper
    is the single chokepoint that maps a ``file_path`` to that
    UUID, creating the row on demand the first time a path is
    visited.

    Args:
        request: Active FastAPI request — for workspace + session
            factory access.
        file_path: Relative notebook path under the workspace's
            notebooks dir.

    Returns:
        The 36-char UUID4 string from ``notebooks.id``.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(Notebook).where(
                Notebook.workspace_id == workspace_id,
                Notebook.file_path == file_path,
            )
        ).scalar_one_or_none()
        if row is not None:
            return str(row.id)
        nb = Notebook(
            id=str(_uuid.uuid4()),
            workspace_id=workspace_id,
            file_path=file_path,
        )
        session.add(nb)
        session.commit()
        return str(nb.id)
