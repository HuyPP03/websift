"""WebSearchClient: search and fetch with SSRF protection."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from web_search.config import MAX_FETCH_BYTES, MAX_PAGE_CHARS, MAX_PDF_FETCH_BYTES
from web_search.content import looks_like_html, looks_like_html_document
from web_search.html import html_to_markdown, truncate
from web_search.http import fetch_raw
from web_search.models import (
    ErrorCategory,
    FetchResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_NON_OWNER_SEGMENTS = {
    "features",
    "pricing",
    "about",
    "contact",
    "login",
    "signup",
    "topics",
    "trending",
    "explore",
    "marketplace",
    "settings",
    "notifications",
    "issues",
    "pulls",
    "discussions",
}

_SEARCH_FOOTER = (
    "\n\n---\n\nIMPORTANT: These are short snippets only. Call fetch(url) with a specific URL to get full page content."
)

_GITHUB_README_HEADERS = {
    "Accept": "application/vnd.github.raw+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def format_search_response(response: SearchResponse) -> str:
    """Format internal search outcome to the public string API."""
    if response.error_category == ErrorCategory.EMPTY_INPUT:
        return "No query provided."
    if response.error_category == ErrorCategory.PROVIDER_IMPORT:
        return response.error_message or "Error: ddgs not installed. Run: pip install ddgs"
    if response.error_category is not None:
        msg = response.error_message or response.error_category
        if msg.startswith("Search failed:"):
            return msg
        return f"Search failed: {msg}"
    if not response.results:
        return "No results found."
    parts = [f"Title: {r.title}\nURL: {r.url}\nSnippet: {r.snippet}" for r in response.results]
    return "\n\n---\n\n".join(parts) + _SEARCH_FOOTER


def format_fetch_result(result: FetchResult) -> str:
    """Format internal fetch outcome to the public string API."""
    if result.error_category is not None:
        return result.error_message or f"Fetch failed: {result.error_category}"
    return result.content


def process_fetched_body(
    body: str,
    content_type: str,
    *,
    max_page_chars: int,
    base_url: str | None = None,
    prefix: str = "",
) -> tuple[str, bool]:
    """Shared body pipeline for ordinary fetch and GitHub README shortcut.

    Returns ``(rendered_text, truncated)``.
    """
    if "html" not in (content_type or "") and not looks_like_html(body):
        text = body.strip()
    else:
        text = html_to_markdown(body, main_content=True, base_url=base_url)
        if not text.strip() and body.strip():
            # Fallback if converter yields empty but raw body is non-empty HTML-ish.
            text = body.strip()

    if prefix:
        text = f"{prefix}{text}"

    pre_len = len(text)
    rendered = truncate(text, max_page_chars)
    truncated = pre_len > max_page_chars
    return rendered, truncated


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
        return format_search_response(self.search_structured(query))

    def fetch(self, url: str) -> str:
        return format_fetch_result(self.fetch_structured(url))

    def search_structured(self, query: str) -> SearchResponse:
        """Internal structured search; public ``search()`` formats this to ``str``."""
        request = SearchRequest(query=(query or "").strip(), max_results=self.max_results)
        if not request.query:
            return SearchResponse(
                request=request,
                error_category=ErrorCategory.EMPTY_INPUT,
                error_message="No query provided.",
            )
        try:
            from ddgs import DDGS
        except ImportError:
            return SearchResponse(
                request=request,
                error_category=ErrorCategory.PROVIDER_IMPORT,
                error_message="Error: ddgs not installed. Run: pip install ddgs",
            )
        try:
            raw = DDGS(timeout=self.timeout).text(request.query, max_results=self.max_results)
        except Exception as e:
            return SearchResponse(
                request=request,
                error_category=ErrorCategory.PROVIDER,
                error_message=f"Search failed: {e}",
            )
        if not raw:
            return SearchResponse(request=request, results=())

        results: list[SearchResult] = []
        for i, row in enumerate(raw, start=1):
            results.append(
                SearchResult(
                    title=str(row.get("title", "") or ""),
                    url=str(row.get("href", "") or ""),
                    snippet=str(row.get("body", "") or ""),
                    rank=i,
                    source="ddgs",
                )
            )
        return SearchResponse(request=request, results=tuple(results))

    def fetch_structured(self, url: str) -> FetchResult:
        """Internal structured fetch; public ``fetch()`` formats this to ``str``."""
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)

        readme_url = self._github_readme_api_url(url)
        if readme_url:
            gh = fetch_raw(
                readme_url,
                self.timeout,
                MAX_FETCH_BYTES,
                MAX_PDF_FETCH_BYTES,
                extra_headers=dict(_GITHUB_README_HEADERS),
            )
            if gh.ok and gh.content.strip():
                # GitHub raw README may be Markdown or HTML document.
                body = gh.content
                ct = gh.content_type
                if looks_like_html_document(body):
                    rendered, truncated = process_fetched_body(
                        body,
                        "text/html",
                        max_page_chars=self.max_page_chars,
                        base_url=url,
                        prefix=f"README of {url} (via GitHub API):\n\n",
                    )
                else:
                    # Preserve Markdown/plain README text with prefix, then truncate.
                    text = f"README of {url} (via GitHub API):\n\n{body.strip()}"
                    pre_len = len(text)
                    rendered = truncate(text, self.max_page_chars)
                    truncated = pre_len > self.max_page_chars
                if rendered.strip():
                    return FetchResult.success(
                        url,
                        rendered,
                        final_url=gh.final_url or readme_url,
                        content_type=ct or "text/plain",
                        status_code=gh.status_code,
                        bytes_read=gh.bytes_read,
                        redirect_count=gh.redirect_count,
                        truncated=truncated,
                    )

        raw = fetch_raw(url, self.timeout, MAX_FETCH_BYTES, MAX_PDF_FETCH_BYTES)
        if not raw.ok:
            return FetchResult.failure(
                url,
                raw.error_message or "Fetch failed",
                raw.error_category or ErrorCategory.UNKNOWN,
                final_url=raw.final_url,
                content_type=raw.content_type,
                status_code=raw.status_code,
                bytes_read=raw.bytes_read,
                redirect_count=raw.redirect_count,
                overflow=raw.overflow,
            )

        rendered, truncated = process_fetched_body(
            raw.content,
            raw.content_type,
            max_page_chars=self.max_page_chars,
            base_url=raw.final_url or url,
        )
        return FetchResult.success(
            url,
            rendered,
            final_url=raw.final_url or url,
            content_type=raw.content_type,
            status_code=raw.status_code,
            bytes_read=raw.bytes_read,
            redirect_count=raw.redirect_count,
            truncated=truncated,
            overflow=raw.overflow,
        )

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
