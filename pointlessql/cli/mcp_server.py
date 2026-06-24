"""CLI entrypoint — run the catalog MCP server over stdio.

Launches the read-only Model Context Protocol server
(:func:`pointlessql.services.mcp_server.build_server`) on the stdio
transport so a local MCP client (an assistant desktop app, an IDE) can
spawn ``pointlessql-mcp`` and browse the lakehouse catalog directly.
"""

from __future__ import annotations

from pointlessql.config import get_settings
from pointlessql.services.mcp_server import build_server
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient


def main() -> None:
    """Build the catalog MCP server and serve it over stdio."""
    settings = get_settings()
    uc_client = UnityCatalogClient(make_soyuz_client(settings))
    build_server(uc_client).run()


if __name__ == "__main__":
    main()
