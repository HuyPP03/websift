"""WebSearchClient: search and fetch with SSRF protection."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace

from websift.config import (
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
from websift.models import (
    ErrorCategory,
    FetchResult,
    SearchRequest,
    SearchResponse,
)
from websift.providers.base import (
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
from websift.providers.brave import BraveProviderConfig
from websift.providers.ddgs import DdgsProviderConfig
from websift.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
    ProviderError,
    ProviderImportError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    sanitize_provider_message,
)
from websift.providers.exa import ExaProviderConfig
from websift.providers.fallback import FallbackSearchProvider
from websift.providers.registry import create_provider, get_default_provider
from websift.providers.searxng import SearxngProviderConfig
from websift.providers.serper import SerperProviderConfig
from websift.providers.tavily import TavilyProviderConfig
from websift.settings import AppSettings, BrowserSettings, ProviderEndpoint, ProviderSettings

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
        allowed_domains=frozenset(getattr(f, "allowed_domains", ()) or ()),
        denied_domains=frozenset(getattr(f, "denied_domains", ()) or ()),
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
        allowed_domains=frozenset(),
        denied_domains=frozenset(),
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

    Configuration options (any combination):

    * Simple kwargs: ``max_results``, ``timeout``, ``max_page_chars``
    * Provider: ``provider="brave"`` (name) or a ``SearchProvider`` instance
    * Timeouts: ``search_timeout`` / ``fetch_timeout`` (override shared ``timeout``)
    * Credentials: ``api_key``, ``base_url`` for keyed/self-hosted providers
    * Filters: ``safe_search``, ``region``, ``time_range``, ``fallback_providers``
    * Extraction: ``include_links``, ``include_images``, ``output_format``, ``native_fetch``
    * Full control: ``settings=AppSettings(...)`` or ``AppSettings.from_env()``
    * Async: ``await client.asearch(...)`` / ``await client.afetch(...)``

    Fetch is owned by the primary search provider (``BaseProvider.fetch``).
    Tavily/Exa may use native extract when configured with an API key.
    """

    def __init__(
        self,
        max_results: int = 5,
        timeout: int = 30,
        max_page_chars: int = MAX_PAGE_CHARS,
        provider: SearchProvider | str | None = None,
        settings: AppSettings | None = None,
        pdf_semaphore=None,
        *,
        search_timeout: float | None = None,
        fetch_timeout: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        fallback_providers: Sequence[str] | None = None,
        safe_search: str | None = None,
        region: str | None = None,
        time_range: str | None = None,
        allow_unsupported_filters: bool | None = None,
        allow_http: bool | None = None,
        native_fetch: bool | None = None,
        fetch_backend: str | None = None,
        include_links: bool | None = None,
        include_images: bool | None = None,
        output_format: str | None = None,
    ):
        provider_obj: SearchProvider | None
        provider_name: str | None
        if isinstance(provider, str):
            provider_obj = None
            provider_name = provider.strip().lower() or None
        else:
            provider_obj = provider
            provider_name = None

        advanced = any(
            v is not None
            for v in (
                search_timeout,
                fetch_timeout,
                api_key,
                base_url,
                fallback_providers,
                safe_search,
                region,
                time_range,
                allow_unsupported_filters,
                allow_http,
                native_fetch,
                fetch_backend,
                include_links,
                include_images,
                output_format,
                provider_name,
            )
        )

        if settings is not None or advanced:
            resolved = _resolve_client_settings(
                base=settings,
                max_results=max_results,
                timeout=timeout,
                max_page_chars=max_page_chars,
                provider_name=provider_name,
                search_timeout=search_timeout,
                fetch_timeout=fetch_timeout,
                api_key=api_key,
                base_url=base_url,
                fallback_providers=fallback_providers,
                safe_search=safe_search,
                region=region,
                time_range=time_range,
                allow_unsupported_filters=allow_unsupported_filters,
                allow_http=allow_http,
                native_fetch=native_fetch,
                fetch_backend=fetch_backend,
                include_links=include_links,
                include_images=include_images,
                output_format=output_format,
                settings_provided=settings is not None,
            )
            resolved.validate()
            self._settings = resolved
            self._pdf_semaphore = pdf_semaphore
            self.max_results = resolved.provider.max_results
            self.timeout = int(resolved.provider.timeout_seconds)
            self.max_page_chars = resolved.extraction.max_page_chars
            self._search_timeout = float(resolved.provider.timeout_seconds)
            self._fetch_timeout = float(resolved.fetch.timeout_seconds)
            self._fetch_context = _fetch_context_from_settings(resolved)
            if provider_obj is not None:
                self._primary_provider = provider_obj
                if isinstance(provider_obj, BaseProvider):
                    provider_obj._fetch_context = self._fetch_context
                    provider_obj._pdf_semaphore = pdf_semaphore
                self._provider = provider_obj
            else:
                self._primary_provider, self._provider = _providers_from_settings(
                    resolved,
                    fetch_context=self._fetch_context,
                    pdf_semaphore=pdf_semaphore,
                )
            self._init_fetch_orchestrator(backend=resolved.fetch.backend)
            self._init_cache(resolved.cache)
        else:
            # Fast legacy path: plain kwargs, default DDGS, no AppSettings tree.
            self._settings = None
            self._pdf_semaphore = pdf_semaphore
            self.max_results = max_results
            self.timeout = timeout
            self.max_page_chars = max_page_chars
            self._search_timeout = float(timeout)
            self._fetch_timeout = float(timeout)
            self._fetch_context = _legacy_fetch_context(timeout=timeout, max_page_chars=max_page_chars)
            if provider_obj is not None:
                self._primary_provider = provider_obj
                if isinstance(provider_obj, BaseProvider):
                    provider_obj._fetch_context = self._fetch_context
                    provider_obj._pdf_semaphore = pdf_semaphore
                self._provider = provider_obj
            else:
                self._primary_provider = get_default_provider(
                    timeout=timeout,
                    fetch_context=self._fetch_context,
                    pdf_semaphore=pdf_semaphore,
                )
                self._provider = self._primary_provider
            self._init_fetch_orchestrator(backend="auto")
            self._init_cache(None)

    def _get_browser_settings(self) -> BrowserSettings | None:
        """Return browser settings from AppSettings or env (legacy path fallback)."""
        if self._settings is not None:
            if self._settings.browser.endpoint:
                return self._settings.browser
            return None
        # Legacy path: read browser settings directly from environment.
        import os

        endpoint = os.environ.get("BROWSER_ENDPOINT", "").strip()
        if not endpoint:
            return None
        return BrowserSettings(
            endpoint=endpoint,
            bearer_token=os.environ.get("BROWSER_TOKEN", "").strip() or None,
            allow_insecure_endpoint=(
                os.environ.get("BROWSER_ALLOW_INSECURE_ENDPOINT", "")
                .lower()
                .strip()
                in ("true", "1", "yes")
            ),
            timeout_seconds=float(os.environ.get("BROWSER_TIMEOUT_SECONDS", "45")),
            post_load_wait_ms=int(os.environ.get("BROWSER_POST_LOAD_WAIT_MS", "500")),
            max_html_bytes=int(os.environ.get("BROWSER_MAX_HTML_BYTES", str(5 * 1024 * 1024))),
            max_response_bytes=int(os.environ.get("BROWSER_MAX_RESPONSE_BYTES", str(6 * 1024 * 1024))),
            max_concurrency=int(os.environ.get("BROWSER_MAX_CONCURRENCY", "4")),
        )

    def _init_fetch_orchestrator(self, *, backend: str) -> None:
        from websift.fetching.backend import CallableFetchBackend
        from websift.fetching.http import HttpFetchBackend
        from websift.fetching.orchestrator import FetchOrchestrator

        provider = self._primary_provider
        native_stage = getattr(provider, "fetch_native", None)
        if not callable(native_stage):
            native_stage = None
        if isinstance(provider, BaseProvider) and (
            native_stage is not None or type(provider).fetch is BaseProvider.fetch
        ):
            http_backend = HttpFetchBackend(self._fetch_context, pdf_semaphore=self._pdf_semaphore)
        else:
            native_stage = None
            http_backend = CallableFetchBackend(
                lambda url: getattr(provider, "fetch")(url),
                fingerprint=f"custom-provider:{type(provider).__module__}.{type(provider).__qualname__}",
            )
        browser_backend = None
        browser_settings = self._get_browser_settings()
        if browser_settings is not None:
            from websift.fetching.browser_client import RemoteBrowserBackend

            browser_backend = RemoteBrowserBackend(browser_settings, self._fetch_context)
        self._browser_backend = browser_backend
        self._fetch_orchestrator = FetchOrchestrator(
            http_backend=http_backend,
            backend=backend,
            browser_backend=browser_backend,
            native_stage=native_stage,
        )

    def close(self) -> None:
        close = getattr(getattr(self, "_browser_backend", None), "close", None)
        if callable(close):
            close()

    def __enter__(self) -> WebSearchClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _init_cache(self, cache_settings) -> None:
        """Wire opt-in cache (memory or disk; disabled unless CacheSettings.enabled)."""
        from websift.cache import DiskTtlCache, TtlLruCache
        from websift.settings import CacheSettings

        if not isinstance(cache_settings, CacheSettings) or not cache_settings.enabled:
            self._cache = None
            self._search_ttl = 0.0
            self._fetch_ttl = 0.0
            return
        backend = (cache_settings.backend or "memory").strip().lower()
        if backend == "disk":
            directory = (cache_settings.directory or "").strip()
            if not directory:
                raise ValueError("CACHE_DIR is required when CACHE_BACKEND=disk")
            self._cache = DiskTtlCache(
                directory,
                max_entries=cache_settings.max_entries,
                max_bytes=cache_settings.max_bytes,
            )
        else:
            self._cache = TtlLruCache(
                max_entries=cache_settings.max_entries,
                max_bytes=cache_settings.max_bytes,
            )
        self._search_ttl = float(cache_settings.search_ttl_seconds)
        self._fetch_ttl = float(cache_settings.fetch_ttl_seconds)

    def search(self, query: str) -> str:
        return format_search_response(self.search_structured(query))

    def fetch(self, url: str) -> str:
        return format_fetch_result(self.fetch_structured(url))

    def search_many(
        self,
        queries: Sequence[str],
        *,
        max_workers: int | None = None,
    ) -> list[SearchResponse]:
        """Run multiple searches concurrently (thread pool; order preserved)."""
        items = [str(q) if q is not None else "" for q in (queries or ())]
        if not items:
            return []
        if len(items) == 1:
            return [self.search_structured(items[0])]

        workers = max_workers
        if workers is None:
            if self._settings is not None:
                workers = int(self._settings.concurrency.search_max)
            else:
                workers = 8
        workers = max(1, min(int(workers), len(items)))

        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[SearchResponse | None] = [None] * len(items)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(self.search_structured, q): i for i, q in enumerate(items)}
            for fut in as_completed(future_map):
                idx = future_map[fut]
                results[idx] = fut.result()
        return [r for r in results if r is not None]

    def search_many_text(
        self,
        queries: Sequence[str],
        *,
        max_workers: int | None = None,
    ) -> list[str]:
        """Like ``search_many`` but formats each response as the public string API."""
        return [format_search_response(r) for r in self.search_many(queries, max_workers=max_workers)]

    async def asearch(self, query: str) -> str:
        """Async search — runs the sync provider path in a worker thread."""
        return await asyncio.to_thread(self.search, query)

    async def afetch(self, url: str) -> str:
        """Async fetch — runs the sync provider path in a worker thread."""
        return await asyncio.to_thread(self.fetch, url)

    async def asearch_structured(self, query: str) -> SearchResponse:
        """Async structured search (same shape as ``search_structured``)."""
        return await asyncio.to_thread(self.search_structured, query)

    async def afetch_structured(self, url: str) -> FetchResult:
        """Async structured fetch (same shape as ``fetch_structured``)."""
        return await asyncio.to_thread(self.fetch_structured, url)

    async def asearch_many(
        self,
        queries: Sequence[str],
        *,
        max_workers: int | None = None,
    ) -> list[SearchResponse]:
        """Async multi-query search (offloads ``search_many`` to a worker thread)."""
        return await asyncio.to_thread(self.search_many, queries, max_workers=max_workers)

    def search_structured(self, query: str) -> SearchResponse:
        """Internal structured search; public ``search()`` formats this to ``str``."""
        from websift.cache import (
            estimate_search_response_size,
            make_search_cache_key,
        )

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

        cache_key = None
        if self._cache is not None and self._search_ttl > 0:
            provider_name = str(getattr(self._provider, "name", None) or "unknown")
            cache_key = make_search_cache_key(request, provider=provider_name)
            hit = self._cache.get(cache_key)
            if isinstance(hit, SearchResponse):
                return hit

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
        response = SearchResponse(request=request, results=tuple(results or ()))
        if cache_key is not None and response.ok and self._cache is not None:
            self._cache.set(
                cache_key,
                response,
                ttl_seconds=self._search_ttl,
                size=estimate_search_response_size(response),
            )
        return response

    def fetch_structured(self, url: str) -> FetchResult:
        """Internal structured fetch; public ``fetch()`` formats this to ``str``.

        Delegates to the primary provider's ``fetch`` (generic by default;
        Tavily/Exa may override with native extract).
        """
        from websift.cache import (
            estimate_fetch_result_size,
            make_fetch_cache_key,
        )
        from websift.security import preflight_fetch_url

        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)

        ctx = self._fetch_context
        ok, reason, preflight = preflight_fetch_url(
            url,
            allow_http=ctx.allow_http,
            allowed_ports=ctx.allowed_ports or None,
            allowed_domains=ctx.allowed_domains or None,
            denied_domains=ctx.denied_domains or None,
        )
        if not ok or preflight is None:
            category = ErrorCategory.BLOCKED
            if "DNS" in reason or "no address found" in reason:
                category = ErrorCategory.NETWORK
            return FetchResult.failure(url, reason, category)
        url = preflight.normalized_url

        cache_key = None
        if self._cache is not None and self._fetch_ttl > 0:
            provider_name = str(getattr(self._primary_provider, "name", None) or "unknown")
            backend = self._settings.fetch.backend if self._settings is not None else "auto"
            cache_key = make_fetch_cache_key(
                url,
                timeout_seconds=float(ctx.timeout_seconds),
                max_bytes=int(ctx.max_bytes),
                max_pdf_bytes=int(ctx.max_pdf_bytes),
                max_redirects=int(ctx.max_redirects),
                max_compressed_bytes=int(ctx.max_compressed_bytes),
                max_decompressed_bytes=int(ctx.max_decompressed_bytes),
                pdf_max_pages=int(ctx.pdf_max_pages),
                pdf_max_chars=int(ctx.pdf_max_chars),
                allow_http=bool(ctx.allow_http),
                allowed_ports=frozenset(ctx.allowed_ports),
                allowed_domains=frozenset(ctx.allowed_domains),
                denied_domains=frozenset(ctx.denied_domains),
                max_page_chars=int(ctx.max_page_chars),
                min_main_content_chars=int(ctx.min_main_content_chars),
                include_links=bool(ctx.include_links),
                include_images=bool(ctx.include_images),
                output_format=str(ctx.output_format),
                native_fetch=bool(ctx.native_fetch),
                backend=backend,
                provider=provider_name,
                implementation_fingerprint=self._fetch_orchestrator.fingerprint,
            )
            hit = self._cache.get(cache_key)
            if isinstance(hit, FetchResult):
                return hit

        try:
            result = self._fetch_orchestrator.fetch(url)
        except ProviderError as e:
            category, message = _provider_error_to_fetch(e)
            return FetchResult.failure(url, message, category)
        except Exception as e:
            return FetchResult.failure(
                url,
                f"Fetch failed: {sanitize_provider_message(str(e))}",
                ErrorCategory.UNKNOWN,
            )
        if cache_key is not None and result.ok and self._cache is not None:
            self._cache.set(
                cache_key,
                result,
                ttl_seconds=self._fetch_ttl,
                size=estimate_fetch_result_size(result),
            )
        return result


def _resolve_client_settings(
    *,
    base: AppSettings | None,
    max_results: int,
    timeout: int,
    max_page_chars: int,
    provider_name: str | None,
    search_timeout: float | None,
    fetch_timeout: float | None,
    api_key: str | None,
    base_url: str | None,
    fallback_providers: Sequence[str] | None,
    safe_search: str | None,
    region: str | None,
    time_range: str | None,
    allow_unsupported_filters: bool | None,
    allow_http: bool | None,
    native_fetch: bool | None,
    fetch_backend: str | None,
    include_links: bool | None,
    include_images: bool | None,
    output_format: str | None,
    settings_provided: bool,
) -> AppSettings:
    """Merge constructor kwargs onto an AppSettings tree.

    Without ``settings``: apply ``max_results`` / ``timeout`` / ``max_page_chars``
    plus any advanced kwargs. With ``settings``: keep the settings tree and only
    overlay non-None advanced kwargs (legacy positional defaults are ignored).
    """
    settings = base if base is not None else AppSettings()
    prov = settings.provider
    fetch = settings.fetch
    extraction = settings.extraction

    if not settings_provided:
        st = float(search_timeout) if search_timeout is not None else float(timeout)
        ft = float(fetch_timeout) if fetch_timeout is not None else float(timeout)
        prov = replace(
            prov,
            max_results=max_results,
            timeout_seconds=st,
            name=provider_name if provider_name is not None else prov.name,
        )
        fetch = replace(fetch, timeout_seconds=ft)
        extraction = replace(extraction, max_page_chars=max_page_chars)
    else:
        if provider_name is not None:
            prov = replace(prov, name=provider_name)
        if search_timeout is not None:
            prov = replace(prov, timeout_seconds=float(search_timeout))
        if fetch_timeout is not None:
            fetch = replace(fetch, timeout_seconds=float(fetch_timeout))

    if fallback_providers is not None:
        prov = replace(
            prov,
            fallback_providers=tuple(str(x).strip() for x in fallback_providers if str(x).strip()),
        )
    if safe_search is not None:
        prov = replace(prov, safe_search=safe_search)
    if region is not None:
        prov = replace(prov, region=region)
    if time_range is not None:
        prov = replace(prov, time_range=time_range)
    if allow_unsupported_filters is not None:
        prov = replace(prov, allow_unsupported_filters=bool(allow_unsupported_filters))
    if allow_http is not None:
        prov = replace(prov, allow_http=bool(allow_http))

    name = (prov.name or "ddgs").strip().lower()
    if api_key is not None or base_url is not None:
        endpoints = dict(prov.endpoints or {})
        prev = endpoints.get(name, ProviderEndpoint())
        endpoints[name] = ProviderEndpoint(
            base_url=base_url if base_url is not None else prev.base_url,
            api_key=api_key if api_key is not None else prev.api_key,
        )
        # Keep primary fields in sync for the selected provider.
        prov = replace(
            prov,
            api_key=api_key if api_key is not None else prov.api_key,
            base_url=base_url if base_url is not None else prov.base_url,
            endpoints=endpoints,
        )

    if native_fetch is not None:
        fetch = replace(fetch, native_fetch=bool(native_fetch))
    if fetch_backend is not None:
        fetch = replace(fetch, backend=str(fetch_backend).strip().lower())
    if include_links is not None:
        extraction = replace(extraction, include_links=bool(include_links))
    if include_images is not None:
        extraction = replace(extraction, include_images=bool(include_images))
    if output_format is not None:
        extraction = replace(extraction, output_format=output_format)

    return replace(settings, provider=prov, fetch=fetch, extraction=extraction)


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
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
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
    if name == "serper":
        return create_provider(
            "serper",
            SerperProviderConfig(
                api_key=ep.api_key or "",
                base_url=ep.base_url or "https://google.serper.dev",
                timeout=float(p.timeout_seconds),
                allow_http=bool(p.allow_http),
                allow_unsupported_filters=p.allow_unsupported_filters,
                retry_max=int(p.retry_max),
                retry_backoff_seconds=float(p.retry_backoff_seconds),
            ),
            **kwargs,
        )
    return create_provider(name, None, **kwargs)
