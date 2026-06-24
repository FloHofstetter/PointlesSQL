"""CLI entrypoint — run the catalog MCP server over stdio.

Launches the Model Context Protocol server
(:func:`pointlessql.services.mcp_server.build_server`) on the stdio
transport so a local MCP client (an assistant desktop app, an IDE) can
spawn ``pointlessql-mcp`` and browse the lakehouse catalog — and, through
the governed ``run_select`` tool, query it. The query runner reuses the
shared Lens gated-SELECT executor (read-only validation, EXPLAIN cost cap,
UC-scoped table resolution) under the default workspace.
"""

from __future__ import annotations

from typing import Any

from pointlessql.config import Settings, get_settings
from pointlessql.services.mcp_server import QueryRunner, build_server
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_query_runner(settings: Settings, uc_client: UnityCatalogClient) -> QueryRunner:
    """Build a governed SELECT runner bound to the default workspace.

    The stdio server bypasses the FastAPI lifespan, so the metadata DB is
    lazy-initialised on first use; queries run statelessly (no Lens session)
    through the shared gated executor.

    Args:
        settings: Resolved application settings.
        uc_client: The UC facade the executor resolves table locations with.

    Returns:
        An async ``(sql, limit) -> result-dict`` runner.
    """

    async def _run(sql: str, limit: int | None) -> dict[str, Any]:
        from pointlessql.db import get_session_factory, init_db
        from pointlessql.services.lens.tools import SessionContext
        from pointlessql.services.lens.tools.query import run_select_query
        from pointlessql.services.workspace._crud import (  # noqa: PLC2701 — default-workspace constant
            DEFAULT_WORKSPACE_ID,
        )

        try:
            factory = get_session_factory()
        except RuntimeError:
            init_db(settings.db.url)
            factory = get_session_factory()
        ctx = SessionContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id=None,
            lens_session_id=None,
            factory=factory,
            settings=settings,
            uc_client=uc_client,
        )
        result = await run_select_query(ctx, sql, limit=limit)
        return result.model_dump()

    return _run


def main() -> None:
    """Build the catalog MCP server (with governed SQL) and serve it over stdio."""
    settings = get_settings()
    uc_client = UnityCatalogClient(make_soyuz_client(settings))
    build_server(uc_client, query_runner=_make_query_runner(settings, uc_client)).run()


if __name__ == "__main__":
    main()
