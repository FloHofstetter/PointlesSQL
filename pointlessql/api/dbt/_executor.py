"""DBT executor factory.

Single-function helper extracted so route handlers don't all need to
know how to build a :class:`DBTExecutor` from request settings.
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.services.dbt import DBTExecutor


def executor(request: Request) -> DBTExecutor:
    """Build a :class:`DBTExecutor` bound to the request's settings."""
    settings = request.app.state.settings
    return DBTExecutor(settings.dbt)
