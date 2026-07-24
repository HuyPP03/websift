"""
websift — Self-contained web search & page fetch utility.

PyPI package, CLI, and import path are all ``websift``.

Usage:
    from websift import WebSearchClient, AppSettings

    client = WebSearchClient()
    client.search("python asyncio tutorial")
    client.fetch("https://docs.python.org/3/library/asyncio.html")

    # Async (worker-thread offload of the sync path)
    await client.asearch("python asyncio")
    await client.afetch("https://docs.python.org/3/")

    # Custom configuration
    client = WebSearchClient(
        max_results=10,
        search_timeout=20,
        fetch_timeout=45,
        max_page_chars=50_000,
        provider="ddgs",
    )
"""

__version__ = "2.0.0"

from websift.client import WebSearchClient
from websift.settings import AppSettings

__all__ = ["WebSearchClient", "AppSettings", "__version__"]
