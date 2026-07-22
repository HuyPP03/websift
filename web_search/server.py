"""MCP server — factory-based, import side-effect free.

Importing this module does **not** read environment variables or create a
runtime client/MCP instance. Call ``create_server()`` or ``main()``.
"""

from __future__ import annotations

import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from web_search.client import WebSearchClient
from web_search.concurrency import WorkLimits
from web_search.settings import AppSettings

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})


def is_loopback_bind(host: str) -> bool:
    h = (host or "").strip().lower().strip("[]")
    return h in _LOOPBACK_HOSTS


def warn_if_public_bind(host: str) -> None:
    """Emit a clear warning when binding outside loopback."""
    if is_loopback_bind(host):
        return
    warnings.warn(
        f"MCP server binding to non-loopback address {host!r}. "
        "This exposes the server on the network; protect it (auth/proxy/firewall) "
        "or set MCP_HOST=127.0.0.1 for local-only access.",
        UserWarning,
        stacklevel=2,
    )


@dataclass
class ServerApp:
    """Runtime MCP server handle."""

    mcp: FastMCP
    client: WebSearchClient
    settings: AppSettings
    limits: WorkLimits
    web_search: Callable[[str], Awaitable[str]]
    web_fetch: Callable[[str], Awaitable[str]]

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
    *,
    limits: WorkLimits | None = None,
    warn_public_bind: bool = True,
) -> ServerApp:
    """Build an MCP server with tools registered under concurrency limits.

    Uses safe defaults when ``settings`` is omitted (does **not** read env).
    Pass ``AppSettings.from_env()`` from process entrypoints.

    Tool schemas stay query/url only — no provider name, base URL, or API key.
    """
    settings = settings if settings is not None else AppSettings()
    settings.validate()
    if warn_public_bind:
        warn_if_public_bind(settings.server.host)

    work = limits if limits is not None else WorkLimits.from_settings(settings.concurrency)

    if client is None:
        client = WebSearchClient(settings=settings, pdf_semaphore=work.pdf_semaphore)
    elif getattr(client, "_pdf_semaphore", None) is None:
        # Attach limiter when caller injects a client without one.
        client._pdf_semaphore = work.pdf_semaphore  # noqa: SLF001 — intentional wiring

    mcp = FastMCP(
        "web-search",
        host=settings.server.host,
        port=settings.server.port,
    )

    @mcp.tool()
    async def web_search(query: str) -> str:
        """Search the web using DuckDuckGo. Returns title, URL, and snippet for each result."""
        return await work.run_search(client.search, query)

    @mcp.tool()
    async def web_fetch(url: str) -> str:
        """Fetch a web page and return its readable text content (HTML -> Markdown, PDF -> text)."""
        return await work.run_fetch(client.fetch, url)

    return ServerApp(
        mcp=mcp,
        client=client,
        settings=settings,
        limits=work,
        web_search=web_search,
        web_fetch=web_fetch,
    )


def main() -> None:
    """Console entry: load env settings and run the MCP server."""
    settings = AppSettings.from_env()
    create_server(settings).run()


if __name__ == "__main__":
    main()
