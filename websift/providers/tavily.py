"""Tavily Search provider — API key required (Authorization Bearer)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from websift.models import ErrorCategory, FetchResult, SearchRequest, SearchResult
from websift.provider_http import ProviderHttpClient, ProviderHttpConfig
from websift.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from websift.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    sanitize_provider_message,
)

_DEFAULT_TAVILY_BASE = "https://api.tavily.com"


@dataclass(frozen=True)
class TavilyProviderConfig:
    api_key: str
    base_url: str = _DEFAULT_TAVILY_BASE
    timeout: float = 30.0
    allow_http: bool = False
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5


class TavilyProvider(BaseProvider):
    """Tavily Search API (`POST /search`) + optional exact-URL extract (`POST /extract`)."""

    name = "tavily"
    capabilities = ProviderCapabilities(
        safe_search=True,
        region=True,
        time_range=True,
        pagination=False,
        domain_filter=False,
    )

    def __init__(
        self,
        config: TavilyProviderConfig | None = None,
        *,
        http: ProviderHttpClient | None = None,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        super().__init__(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
        if config is None:
            raise ProviderConfigError("Tavily API key is required.", code="missing_api_key", provider="tavily")
        key = (config.api_key or "").strip()
        if not key and http is None:
            raise ProviderConfigError("Tavily API key is required.", code="missing_api_key", provider=self.name)
        self.config = config
        if http is not None:
            self._http = http
        else:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            self._http = ProviderHttpClient(
                ProviderHttpConfig(
                    base_url=config.base_url or _DEFAULT_TAVILY_BASE,
                    timeout=config.timeout,
                    headers=headers,
                    allow_http=config.allow_http,
                    retry_max=config.retry_max,
                    retry_backoff_seconds=config.retry_backoff_seconds,
                )
            )

    def search(self, request: SearchRequest) -> list[SearchResult]:
        validate_request_capabilities(
            request,
            self.capabilities,
            allow_unsupported=self.config.allow_unsupported_filters,
        )
        count = max(1, min(int(request.max_results or 5), 20))
        body: dict[str, object] = {
            "query": request.query,
            "max_results": count,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        safe = _map_tavily_safe_search(request.safe_search)
        if safe is not None:
            body["safe_search"] = safe
        if request.region:
            body["country"] = request.region
        time_range = _map_tavily_time_range(request.time_range)
        if time_range is not None:
            body["time_range"] = time_range

        payload = self._http.post_json("/search", json_body=body, provider=self.name)
        if payload is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)
        if not isinstance(payload, dict):
            raise ProviderResponseError("Provider returned non-object JSON.", provider=self.name)

        rows = payload.get("results") or []
        if not isinstance(rows, list):
            raise ProviderResponseError("Provider results field is not a list.", provider=self.name)

        out: list[SearchResult] = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "") or "")
            url = str(row.get("url", "") or "")
            snippet = str(row.get("content", "") or row.get("snippet", "") or "")
            out.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    rank=i,
                    source=self.name,
                )
            )
            if len(out) >= count:
                break
        return out

    def fetch_native(self, url: str) -> FetchResult | None:
        """Run only Tavily extraction; return None when generic HTTP should follow."""
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)
        if not self._fetch_context.native_fetch or not (self.config.api_key or "").strip():
            return None

        blocked = self.validate_url_for_provider(url)
        if blocked is not None:
            return blocked

        try:
            return self._extract_url(url)
        except (ProviderAuthError, ProviderConfigError, ProviderBillingError, ProviderRateLimitError) as e:
            return _fetch_provider_failure(url, e)
        except ProviderError:
            return None

    def fetch(self, url: str) -> FetchResult:
        url = (url or "").strip()
        native = self.fetch_native(url)
        if native is not None:
            return native
        return super().fetch(url)

    def _extract_url(self, url: str) -> FetchResult | None:
        """POST /extract for one URL. Returns success result, or None for URL-level failure."""
        body: dict[str, object] = {
            "urls": [url],
            "format": "markdown",
            "extract_depth": "basic",
            "include_images": False,
        }
        payload = self._http.post_json("/extract", json_body=body, provider=self.name)
        if payload is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)
        if not isinstance(payload, dict):
            raise ProviderResponseError("Provider returned non-object JSON.", provider=self.name)

        results = payload.get("results")
        failed = payload.get("failed_results")
        if results is not None and not isinstance(results, list):
            raise ProviderResponseError("Provider results field is not a list.", provider=self.name)
        if failed is not None and not isinstance(failed, list):
            raise ProviderResponseError("Provider failed_results field is not a list.", provider=self.name)

        for row in results or []:
            if not isinstance(row, dict):
                continue
            row_url = str(row.get("url", "") or "")
            if row_url and not _urls_match(row_url, url):
                # Prefer exact match when multiple; still accept first if only one.
                if len(results or []) > 1:
                    continue
            content = str(row.get("raw_content", "") or "")
            if content.strip():
                return self.truncate_native_content(
                    url,
                    content,
                    final_url=row_url or url,
                    content_type="text/markdown",
                )

        # URL-level failure when listed in failed_results or empty successful payload.
        for row in failed or []:
            if not isinstance(row, dict):
                continue
            row_url = str(row.get("url", "") or "")
            if not row_url or _urls_match(row_url, url):
                return None
        if not results and not failed:
            raise ProviderResponseError("Provider extract response missing results.", provider=self.name)
        return None


def _urls_match(a: str, b: str) -> bool:
    pa, pb = urlparse(a.strip()), urlparse(b.strip())
    host_a = (pa.hostname or "").lower().lstrip("www.")
    host_b = (pb.hostname or "").lower().lstrip("www.")
    path_a = (pa.path or "/").rstrip("/") or "/"
    path_b = (pb.path or "/").rstrip("/") or "/"
    return host_a == host_b and path_a == path_b


def _fetch_provider_failure(url: str, exc: ProviderError) -> FetchResult:
    msg = sanitize_provider_message(exc.message or str(exc))
    if isinstance(exc, ProviderAuthError):
        category = ErrorCategory.AUTH
    elif isinstance(exc, ProviderRateLimitError):
        category = ErrorCategory.RATE_LIMIT
    elif isinstance(exc, ProviderBillingError):
        category = ErrorCategory.PROVIDER
    else:
        category = ErrorCategory.PROVIDER
    if not msg.startswith("Fetch failed:"):
        msg = f"Fetch failed: {msg}"
    return FetchResult.failure(url, msg, category)


def _map_tavily_safe_search(value: str | None) -> bool | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null"}:
        return None
    if v in {"0", "off", "false", "no"}:
        return False
    if v in {"1", "2", "on", "true", "yes", "strict", "moderate", "medium"}:
        return True
    return None


def _map_tavily_time_range(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null", "any", "all"}:
        return None
    aliases = {
        "d": "day",
        "day": "day",
        "past_day": "day",
        "pd": "day",
        "w": "week",
        "week": "week",
        "past_week": "week",
        "pw": "week",
        "m": "month",
        "month": "month",
        "past_month": "month",
        "pm": "month",
        "y": "year",
        "year": "year",
        "past_year": "year",
        "py": "year",
    }
    return aliases.get(v)
