"""Shared helpers used across the runs_routes sub-modules.

The detail / list / rollback / diff sub-modules all need to load a
single :class:`AgentRun` ORM row by id.  Centralising the loader
here keeps the import graph one-way: every sub-module depends on
``_shared``, and ``_shared`` depends on nothing else inside the
package.

func:`pointlessql.api.dependencies.get_templates` under its old name
so existing sub-modules keep working without churn.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import get_templates as templates
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.agent._runs import AgentRun

__all__ = ["templates", "load_run"]


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
