"""SQL-editor chat REST + WS routes.

This package owns every non-static surface the chat drawer talks
to:

* :mod:`_propose` — ``POST /api/sql/chat/{session_id}/propose``,
  called by the ``pql_propose_sql`` plugin tool to drop a DML/DDL
  draft into the editor.
* Future modules (Day 6): ``_accept`` / ``_discard``,
  ``_history`` (GET conversation snapshot for WS reconnect).

The package re-exports a single ``router`` that
:func:`pointlessql.api._bootstrap._routers.register_routers`
mounts.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sql_chat_routes import _accept, _propose

router = APIRouter(tags=["sql-chat"])
router.include_router(_propose.router)
router.include_router(_accept.router)

__all__ = ["router"]
