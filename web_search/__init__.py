"""
web_search - Self-contained web search & page fetch utility.

Package name on PyPI/CLI: ``websift``. Import path: ``web_search``.

Usage:
    from web_search import WebSearchClient

    client = WebSearchClient()
    client.search("python asyncio tutorial")
    client.fetch("https://docs.python.org/3/library/asyncio.html")
"""

__version__ = "0.3.0"

from web_search.client import WebSearchClient

__all__ = ["WebSearchClient", "__version__"]
