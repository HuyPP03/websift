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
)
from web_search.providers.base import SearchProvider
from web_search.providers.brave import BraveProviderConfig
from web_search.providers.ddgs import DdgsProviderConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderImportError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    sanitize_provider_message,
)
from web_search.providers.exa import ExaProviderConfig
from web_search.providers.fallback import FallbackSearchProvider
from web_search.providers.registry import create_provider, get_default_provider
from web_search.providers.searxng import SearxngProviderConfig
from web_search.providers.tavily import TavilyProviderConfig
from web_search.settings import AppSettings, ProviderSettings

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


def _provider_error_to_response(exc: ProviderError) -> tuple[str, str]:
    """Map provider exceptions to (ErrorCategory, public error_message)."""
    msg = sanitize_provider_message(exc.message or str(exc))
    if isinstance(exc, ProviderImportError):
        return ErrorCategory.PROVIDER_IMPORT, msg
    if isinstance(exc, ProviderAuthError):
        category = ErrorCategory.AUTH
    elif isinstance(exc, ProviderRateLimitError):
        category = ErrorCategory.RATE_LIMIT
    elif isinstance(exc, ProviderTimeoutError):
        category = ErrorCategory.TIMEOUT
    elif isinstance(exc, ProviderUnavailableError):
        category = ErrorCategory.UNAVAILABLE
    else:
        category = ErrorCategory.PROVIDER
    if msg.startswith("Search failed:") or msg.startswith("Error:"):
        return category, msg
    return category, f"Search failed: {msg}"


class WebSearchClient:
    """
    Self-contained web search + page fetch.
    No API key required. Uses DuckDuckGo (ddgs) for search by default,
    urllib for fetch, with SSRF protection + DNS pinning.

    Prefer ``WebSearchClient(settings=AppSettings.from_env())`` for runtime
    configuration. Legacy ``max_results`` / ``timeout`` / ``max_page_chars``
    kwargs remain supported and map search+fetch to the shared timeout.
    """

    def __init__(
        self,
        max_results: int = 5,
        timeout: int = 30,
        max_page_chars: int = MAX_PAGE_CHARS,
        provider: SearchProvider | None = None,
        settings: AppSettings | None = None,
        pdf_semaphore=None,
    ):
        self._settings = settings
        self._pdf_semaphore = pdf_semaphore
        if settings is not None:
            self.max_results = settings.provider.max_results
            # Public attribute kept for compatibility; equals search timeout.
            self.timeout = int(settings.provider.timeout_seconds)
            self.max_page_chars = settings.extraction.max_page_chars
            self._search_timeout = float(settings.provider.timeout_seconds)
            self._fetch_timeout = float(settings.fetch.timeout_seconds)
            self._max_fetch_bytes = settings.fetch.max_bytes
            self._max_pdf_fetch_bytes = settings.fetch.max_pdf_bytes
            if provider is not None:
                self._provider = provider
            else:
                self._provider = _provider_from_settings(settings)
        else:
            self.max_results = max_results
            self.timeout = timeout
            self.max_page_chars = max_page_chars
            self._search_timeout = float(timeout)
            self._fetch_timeout = float(timeout)
            self._max_fetch_bytes = MAX_FETCH_BYTES
            self._max_pdf_fetch_bytes = MAX_PDF_FETCH_BYTES
            self._provider = provider if provider is not None else get_default_provider(timeout=timeout)

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
        if self._settings is not None:
            ps = self._settings.provider
            request = SearchRequest(
                query=request.query,
                max_results=self.max_results,
                safe_search=ps.safe_search,
                region=ps.region,
                time_range=ps.time_range,
            )
        try:
            results = self._provider.search(request)
        except ProviderError as e:
            category, message = _provider_error_to_response(e)
            return SearchResponse(
                request=request,
                error_category=category,
                error_message=message,
            )
        except Exception as e:
            return SearchResponse(
                request=request,
                error_category=ErrorCategory.PROVIDER,
                error_message=f"Search failed: {sanitize_provider_message(str(e))}",
            )
        return SearchResponse(request=request, results=tuple(results or ()))

    def fetch_structured(self, url: str) -> FetchResult:
        """Internal structured fetch; public ``fetch()`` formats this to ``str``."""
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)

        fetch_timeout = self._fetch_timeout
        max_bytes = self._max_fetch_bytes
        max_pdf = self._max_pdf_fetch_bytes

        readme_url = self._github_readme_api_url(url)
        if readme_url:
            gh = fetch_raw(
                readme_url,
                fetch_timeout,
                max_bytes,
                max_pdf,
                extra_headers=dict(_GITHUB_README_HEADERS),
                pdf_semaphore=self._pdf_semaphore,
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

        raw = fetch_raw(
            url,
            fetch_timeout,
            max_bytes,
            max_pdf,
            pdf_semaphore=self._pdf_semaphore,
        )
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


def _provider_from_settings(settings: AppSettings) -> SearchProvider:
    name = (settings.provider.name or "ddgs").strip().lower()
    primary = _single_provider_from_settings(name, settings.provider)
    fallbacks: list[SearchProvider] = []
    seen = {name}
    for raw in settings.provider.fallback_providers:
        fb = (raw or "").strip().lower()
        if not fb or fb in seen:
            continue
        fallbacks.append(_single_provider_from_settings(fb, settings.provider))
        seen.add(fb)
    if not fallbacks:
        return primary
    return FallbackSearchProvider([primary, *fallbacks])


def _single_provider_from_settings(name: str, p: ProviderSettings) -> SearchProvider:
    ep = p.endpoint(name)
    if name == "ddgs":
        return create_provider(
            "ddgs",
            DdgsProviderConfig(
                timeout=int(p.timeout_seconds),
                allow_unsupported_filters=p.allow_unsupported_filters,
            ),
        )
    if name == "searxng":
        return create_provider(
            "searxng",
            SearxngProviderConfig(
                base_url=ep.base_url or "",
                api_key=ep.api_key,
                timeout=float(p.timeout_seconds),
                allow_http=bool(p.allow_http),
                allow_unsupported_filters=p.allow_unsupported_filters,
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
            ),
        )
    if name == "brave":
        return create_provider(
            "brave",
            BraveProviderConfig(
                api_key=ep.api_key or "",
                base_url=ep.base_url or "https://api.search.brave.com",
                timeout=float(p.timeout_seconds),
                allow_http=bool(p.allow_http),
                allow_unsupported_filters=p.allow_unsupported_filters,
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
            ),
        )
    if name == "tavily":
        return create_provider(
            "tavily",
            TavilyProviderConfig(
                api_key=ep.api_key or "",
                base_url=ep.base_url or "https://api.tavily.com",
                timeout=float(p.timeout_seconds),
                allow_http=bool(p.allow_http),
                allow_unsupported_filters=p.allow_unsupported_filters,
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
            ),
        )
    if name == "exa":
        return create_provider(
            "exa",
            ExaProviderConfig(
                api_key=ep.api_key or "",
                base_url=ep.base_url or "https://api.exa.ai",
                timeout=float(p.timeout_seconds),
                allow_http=bool(p.allow_http),
                allow_unsupported_filters=p.allow_unsupported_filters,
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
            ),
        )
    return create_provider(name, None)
