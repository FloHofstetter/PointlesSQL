"""Shared helpers used across the runs_routes sub-modules.

The detail / list / rollback / diff sub-modules all need a way to
fetch the shared :class:`Jinja2Templates` instance off ``app.state``
and to load a single :class:`AgentRun` ORM row by id.  Centralising
those tiny helpers here keeps the import graph one-way: every
sub-module depends on ``_shared``, and ``_shared`` depends on
nothing else inside the package.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.agent._runs import AgentRun


def templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def load_run(request: Request, run_id: str) -> AgentRun:
    """Load a single agent-run row or raise :class:`CatalogNotFoundError`.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string from the URL.

    Returns:
        The detached ORM row.

    Raises:
        CatalogNotFoundError: No run with that id exists.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        session.expunge(row)
        return row
