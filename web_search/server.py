"""MCP server module for web_search — can be run standalone or imported as a library."""

import asyncio
import os

from mcp.server.fastmcp import FastMCP

from web_search.client import WebSearchClient

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8787"))
TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")  # streamable-http | sse | stdio

mcp = FastMCP("web-search", host=HOST, port=PORT)

_client = WebSearchClient(
    max_results=int(os.getenv("SEARCH_MAX_RESULTS", "5")),
    timeout=int(os.getenv("SEARCH_TIMEOUT", "30")),
)


@mcp.tool()
async def web_search(query: str) -> str:
    """Search the web using DuckDuckGo. Returns title, URL, and snippet for each result."""
    return await asyncio.to_thread(_client.search, query)


@mcp.tool()
async def web_fetch(url: str) -> str:
    """Fetch a web page and return its readable text content (HTML -> Markdown, PDF -> text)."""
    return await asyncio.to_thread(_client.fetch, url)


def main():
    """Entry point for the web-search-server console script."""
    mcp.run(transport=TRANSPORT)


if __name__ == "__main__":
    main()
