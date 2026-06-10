"""Shared helpers for the route package."""

from __future__ import annotations

import logging

from fastapi import Request

from pointlessql.api._dbx_error_wrapper import (
    DbxApiError as DbxApiError,
)
from pointlessql.api._dbx_error_wrapper import (
    dbx_error_response as dbx_error_response,
)
from pointlessql.api._dbx_error_wrapper import (
    wrap_dbx as wrap_dbx,
)

logger = logging.getLogger(__name__)


def require_enabled(request: Request) -> None:
    """Reject every call with 503 when the API is disabled by settings."""
    settings = request.app.state.settings
    if not settings.sql_execution_api.enabled:
        raise DbxApiError(
            503,
            {
                "error_code": "WORKSPACE_TEMPORARILY_UNAVAILABLE",
                "message": "The SQL Statement Execution API is disabled on this deployment.",
            },
        )
