"""Notebook-editor AI-assistant REST surface (Phase 96).

Two child route modules:

* :mod:`_propose` — ``POST /api/notebook/chat/{id}/propose-cell``,
  ``/fix-cell``, ``/explain-cell``.  Writes a
  :class:`NotebookCellProposal` row + fans out a
  ``cell_proposal_created`` broker event.
* :mod:`_accept` — ``POST /api/notebook/chat/proposals/{id}/accept``,
  ``/discard``, and ``GET /api/notebook/chat/cell/{cell_uuid}/explanations``.

All routes mount on the top-level FastAPI app via the package's
:attr:`router` aggregator, included in
:mod:`pointlessql.api._bootstrap._routers`.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.notebook_chat_routes import _accept, _propose

router = APIRouter()
router.include_router(_propose.router)
router.include_router(_accept.router)

__all__ = ["router"]
