"""WebSearchClient: search and fetch with SSRF protection."""

from __future__ import annotations

from web_search.config import (
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_FETCH_BYTES,
    MAX_PAGE_CHARS,
    MAX_PDF_FETCH_BYTES,
    MAX_REDIRECTS,
    MIN_MAIN_CONTENT_CHARS,
    PDF_MAX_CHARS,
    PDF_MAX_PAGES,
)
from web_search.models import (
    ErrorCategory,
    FetchResult,
    SearchRequest,
    SearchResponse,
)
from web_search.providers.base import (
    GITHUB_README_HEADERS,
    BaseProvider,
    FetchContext,
    SearchProvider,
    process_fetched_body,
)

# Re-exports used by tests and callers.
__all__ = [
    "WebSearchClient",
    "format_fetch_result",
    "format_search_response",
    "process_fetched_body",
]
from web_search.providers.brave import BraveProviderConfig
from web_search.providers.ddgs import DdgsProviderConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
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

# Backward-compatible alias for tests/docs that import the old name.
_GITHUB_README_HEADERS = GITHUB_README_HEADERS

_SEARCH_FOOTER = (
    "\n\n---\n\nIMPORTANT: These are short snippets only. Call fetch(url) with a specific URL to get full page content."
)


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
    elif isinstance(exc, ProviderBillingError):
        category = ErrorCategory.PROVIDER
    else:
        category = ErrorCategory.PROVIDER
    if msg.startswith("Search failed:") or msg.startswith("Error:"):
        return category, msg
    return category, f"Search failed: {msg}"


def _provider_error_to_fetch(exc: ProviderError) -> tuple[str, str]:
    """Map provider exceptions raised during fetch to public fetch errors."""
    msg = sanitize_provider_message(exc.message or str(exc))
    if isinstance(exc, ProviderAuthError):
        category = ErrorCategory.AUTH
    elif isinstance(exc, ProviderRateLimitError):
        category = ErrorCategory.RATE_LIMIT
    elif isinstance(exc, ProviderTimeoutError):
        category = ErrorCategory.TIMEOUT
    elif isinstance(exc, ProviderUnavailableError):
        category = ErrorCategory.UNAVAILABLE
    elif isinstance(exc, ProviderBillingError):
        category = ErrorCategory.PROVIDER
    else:
        category = ErrorCategory.PROVIDER
    if msg.startswith("Fetch failed:") or msg.startswith("Error:"):
        return category, msg
    return category, f"Fetch failed: {msg}"


def _fetch_context_from_settings(settings: AppSettings) -> FetchContext:
    f = settings.fetch
    e = settings.extraction
    return FetchContext(
        timeout_seconds=float(f.timeout_seconds),
        max_bytes=int(f.max_bytes),
        max_pdf_bytes=int(f.max_pdf_bytes),
        max_redirects=int(f.max_redirects),
        max_compressed_bytes=int(f.max_compressed_bytes),
        max_decompressed_bytes=int(f.max_decompressed_bytes),
        pdf_max_pages=int(f.pdf_max_pages),
        pdf_max_chars=int(f.pdf_max_chars),
        allow_http=bool(f.allow_http),
        allowed_ports=frozenset(f.allowed_ports or ()),
        max_page_chars=int(e.max_page_chars),
        min_main_content_chars=int(e.min_main_content_chars),
        include_links=bool(e.include_links),
        include_images=bool(e.include_images),
        output_format=e.output_format,
        native_fetch=bool(getattr(f, "native_fetch", True)),
    )


def _legacy_fetch_context(
    *,
    timeout: int,
    max_page_chars: int,
) -> FetchContext:
    return FetchContext(
        timeout_seconds=float(timeout),
        max_bytes=MAX_FETCH_BYTES,
        max_pdf_bytes=MAX_PDF_FETCH_BYTES,
        max_redirects=MAX_REDIRECTS,
        max_compressed_bytes=MAX_COMPRESSED_BYTES,
        max_decompressed_bytes=MAX_DECOMPRESSED_BYTES,
        pdf_max_pages=PDF_MAX_PAGES,
        pdf_max_chars=PDF_MAX_CHARS,
        allow_http=True,
        allowed_ports=frozenset(),
        max_page_chars=max_page_chars,
        min_main_content_chars=MIN_MAIN_CONTENT_CHARS,
        include_links=True,
        include_images=False,
        output_format="markdown",
        native_fetch=True,
    )


class WebSearchClient:
    """
    Self-contained web search + page fetch.
    No API key required. Uses DuckDuckGo (ddgs) for search by default,
    urllib for fetch, with SSRF protection + DNS pinning.

    Prefer ``WebSearchClient(settings=AppSettings.from_env())`` for runtime
    configuration. Legacy ``max_results`` / ``timeout`` / ``max_page_chars``
    kwargs remain supported and map search+fetch to the shared timeout.

    Fetch is owned by the primary search provider (``BaseProvider.fetch``).
    Tavily/Exa may use native extract when configured with an API key.
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
            self._fetch_context = _fetch_context_from_settings(settings)
            if provider is not None:
                self._primary_provider = provider
                if isinstance(provider, BaseProvider):
                    provider._fetch_context = self._fetch_context
                    provider._pdf_semaphore = pdf_semaphore
                self._provider = provider
            else:
                self._primary_provider, self._provider = _providers_from_settings(
                    settings,
                    fetch_context=self._fetch_context,
                    pdf_semaphore=pdf_semaphore,
                )
        else:
            self.max_results = max_results
            self.timeout = timeout
            self.max_page_chars = max_page_chars
            self._search_timeout = float(timeout)
            self._fetch_timeout = float(timeout)
            self._fetch_context = _legacy_fetch_context(timeout=timeout, max_page_chars=max_page_chars)
            if provider is not None:
                self._primary_provider = provider
                if isinstance(provider, BaseProvider):
                    provider._fetch_context = self._fetch_context
                    provider._pdf_semaphore = pdf_semaphore
                self._provider = provider
            else:
                self._primary_provider = get_default_provider(
                    timeout=timeout,
                    fetch_context=self._fetch_context,
                    pdf_semaphore=pdf_semaphore,
                )
                self._provider = self._primary_provider

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
        """Internal structured fetch; public ``fetch()`` formats this to ``str``.

        Delegates to the primary provider's ``fetch`` (generic by default;
        Tavily/Exa may override with native extract).
        """
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)
        try:
            return self._primary_provider.fetch(url)
        except ProviderError as e:
            category, message = _provider_error_to_fetch(e)
            return FetchResult.failure(url, message, category)
        except Exception as e:
            return FetchResult.failure(
                url,
                f"Fetch failed: {sanitize_provider_message(str(e))}",
                ErrorCategory.UNKNOWN,
            )


def _providers_from_settings(
    settings: AppSettings,
    *,
    fetch_context: FetchContext,
    pdf_semaphore=None,
) -> tuple[SearchProvider, SearchProvider]:
    """Return ``(primary, search_provider)`` where search_provider may be a fallback chain."""
    name = (settings.provider.name or "ddgs").strip().lower()
    primary = _single_provider_from_settings(
        name,
        settings.provider,
        fetch_context=fetch_context,
        pdf_semaphore=pdf_semaphore,
    )
    fallbacks: list[SearchProvider] = []
    seen = {name}
    for raw in settings.provider.fallback_providers:
        fb = (raw or "").strip().lower()
        if not fb or fb in seen:
            continue
        fallbacks.append(
            _single_provider_from_settings(
                fb,
                settings.provider,
                fetch_context=fetch_context,
                pdf_semaphore=pdf_semaphore,
            )
        )
        seen.add(fb)
    if not fallbacks:
        return primary, primary
    chain = FallbackSearchProvider(
        [primary, *fallbacks],
        fetch_context=fetch_context,
        pdf_semaphore=pdf_semaphore,
    )
    return primary, chain


def _single_provider_from_settings(
    name: str,
    p: ProviderSettings,
    *,
    fetch_context: FetchContext,
    pdf_semaphore=None,
) -> SearchProvider:
    ep = p.endpoint(name)
    kwargs = {"fetch_context": fetch_context, "pdf_semaphore": pdf_semaphore}
    if name == "ddgs":
        return create_provider(
            "ddgs",
            DdgsProviderConfig(
                timeout=int(p.timeout_seconds),
                allow_unsupported_filters=p.allow_unsupported_filters,
            ),
            **kwargs,
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
            **kwargs,
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
            **kwargs,
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
            **kwargs,
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
            **kwargs,
        )
    return create_provider(name, None, **kwargs)
