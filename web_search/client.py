"""WebSearchClient: search and fetch with SSRF protection."""

import re
from typing import Optional
from urllib.parse import urlparse

from web_search.config import MAX_FETCH_BYTES, MAX_PAGE_CHARS, MAX_PDF_FETCH_BYTES
from web_search.content import looks_like_html, looks_like_html_document
from web_search.html import html_to_markdown, truncate
from web_search.http import fetch_raw

_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_NON_OWNER_SEGMENTS = {
    "features", "pricing", "about", "contact", "login", "signup",
    "topics", "trending", "explore", "marketplace", "settings",
    "notifications", "issues", "pulls", "discussions",
}


class WebSearchClient:
    """
    Self-contained web search + page fetch.
    No API key required. Uses DuckDuckGo (ddgs) for search,
    urllib for fetch, with SSRF protection + DNS pinning.
    """

    def __init__(
        self,
        max_results: int = 5,
        timeout: int = 30,
        max_page_chars: int = MAX_PAGE_CHARS,
    ):
        self.max_results = max_results
        self.timeout = timeout
        self.max_page_chars = max_page_chars

    def search(self, query: str) -> str:
        if not query or not query.strip():
            return "No query provided."
        try:
            from ddgs import DDGS
        except ImportError:
            return "Error: ddgs not installed. Run: pip install ddgs"
        try:
            results = DDGS(timeout=self.timeout).text(query.strip(), max_results=self.max_results)
        except Exception as e:
            return f"Search failed: {e}"
        if not results:
            return "No results found."
        parts = [
            f"Title: {r.get('title', '')}\nURL: {r.get('href', '')}\nSnippet: {r.get('body', '')}"
            for r in results
        ]
        return "\n\n---\n\n".join(parts) + (
            "\n\n---\n\nIMPORTANT: These are short snippets only. "
            "Call fetch(url) with a specific URL to get full page content."
        )

    def fetch(self, url: str) -> str:
        url = url.strip()
        if not url:
            return "No URL provided."

        readme_url = self._github_readme_api_url(url)
        if readme_url:
            err, body, _ = fetch_raw(
                readme_url, self.timeout, MAX_FETCH_BYTES, MAX_PDF_FETCH_BYTES,
                extra_headers={
                    "Accept": "application/vnd.github.raw+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if err is None and body.strip():
                content = html_to_markdown(body, main_content=True) if looks_like_html_document(body) else body
                if content.strip():
                    return truncate(f"README of {url} (via GitHub API):\n\n{content}", self.max_page_chars)

        err, body, content_type = fetch_raw(url, self.timeout, MAX_FETCH_BYTES, MAX_PDF_FETCH_BYTES)
        if err is not None:
            return err

        if "html" not in content_type and not looks_like_html(body):
            return truncate(body.strip(), self.max_page_chars)

        return truncate(html_to_markdown(body, main_content=True), self.max_page_chars)

    def _github_readme_api_url(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().lstrip("www.")
        if host != "github.com":
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2:
            return None
        owner, repo = parts
        if owner.lower() in _GITHUB_NON_OWNER_SEGMENTS:
            return None
        if repo.endswith(".git"):
            repo = repo[:-4]
        if not (_GITHUB_NAME_RE.match(owner) and _GITHUB_NAME_RE.match(repo)):
            return None
        return f"https://api.github.com/repos/{owner}/{repo}/readme"
