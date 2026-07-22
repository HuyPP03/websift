"""MCP server — factory-based, import side-effect free.

Importing this module does **not** read environment variables or create a
runtime client/MCP instance. Call ``create_server()`` or ``main()``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from web_search.client import WebSearchClient
from web_search.settings import AppSettings


@dataclass
class ServerApp:
    """Runtime MCP server handle."""

    mcp: FastMCP
    client: WebSearchClient
    settings: AppSettings

    @property
    def host(self) -> str:
        return self.settings.server.host

    @property
    def port(self) -> int:
        return self.settings.server.port

    @property
    def transport(self) -> str:
        return self.settings.server.transport

    def run(self, transport: str | None = None) -> None:
        self.mcp.run(transport=transport or self.transport)


def create_server(
    settings: AppSettings | None = None,
    client: WebSearchClient | None = None,
) -> ServerApp:
    """Build an MCP server with tools registered.

    Uses safe defaults when ``settings`` is omitted (does **not** read env).
    Pass ``AppSettings.from_env()`` from process entrypoints.
    """
    settings = settings if settings is not None else AppSettings()
    settings.validate()
    client = client if client is not None else WebSearchClient(settings=settings)

    mcp = FastMCP(
        "web-search",
        host=settings.server.host,
        port=settings.server.port,
    )

    @mcp.tool()
    async def web_search(query: str) -> str:
        """Search the web using DuckDuckGo. Returns title, URL, and snippet for each result."""
        return await asyncio.to_thread(client.search, query)

    @mcp.tool()
    async def web_fetch(url: str) -> str:
        """Fetch a web page and return its readable text content (HTML -> Markdown, PDF -> text)."""
        return await asyncio.to_thread(client.fetch, url)

    # Attach tool callables for tests / programmatic access
    app = ServerApp(mcp=mcp, client=client, settings=settings)
    app.web_search = web_search  # type: ignore[attr-defined]
    app.web_fetch = web_fetch  # type: ignore[attr-defined]
    return app


def main() -> None:
    """Console entry: load env settings and run the MCP server."""
    settings = AppSettings.from_env()
    create_server(settings).run()


if __name__ == "__main__":
    main()
