"""Brave Search provider — API key required (X-Subscription-Token)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_search.models import SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import ProviderConfigError, ProviderResponseError

_DEFAULT_BRAVE_BASE = "https://api.search.brave.com"


@dataclass(frozen=True)
class BraveProviderConfig:
    api_key: str
    base_url: str = _DEFAULT_BRAVE_BASE
    timeout: float = 30.0
    allow_http: bool = False
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5


class BraveProvider(BaseProvider):
    """Brave Web Search API (`/res/v1/web/search`)."""

    name = "brave"
    capabilities = ProviderCapabilities(
        safe_search=True,
        region=True,
        time_range=True,
        pagination=False,
        domain_filter=False,
    )

    def __init__(
        self,
        config: BraveProviderConfig | None = None,
        *,
        http: ProviderHttpClient | None = None,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        super().__init__(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
        if config is None:
            raise ProviderConfigError("Brave API key is required.", code="missing_api_key", provider="brave")
        key = (config.api_key or "").strip()
        if not key and http is None:
            raise ProviderConfigError("Brave API key is required.", code="missing_api_key", provider=self.name)
        self.config = config
        if http is not None:
            self._http = http
        else:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "X-Subscription-Token": key,
            }
            self._http = ProviderHttpClient(
                ProviderHttpConfig(
                    base_url=config.base_url or _DEFAULT_BRAVE_BASE,
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
        params: dict[str, object] = {"q": request.query, "count": count}
        safesearch = _map_brave_safesearch(request.safe_search)
        if safesearch is not None:
            params["safesearch"] = safesearch
        if request.region:
            params["country"] = request.region
        freshness = _map_brave_freshness(request.time_range)
        if freshness is not None:
            params["freshness"] = freshness

        payload = self._http.get_json("/res/v1/web/search", params=params, provider=self.name)
        if payload is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)
        if not isinstance(payload, dict):
            raise ProviderResponseError("Provider returned non-object JSON.", provider=self.name)

        web = payload.get("web") or {}
        if not isinstance(web, dict):
            raise ProviderResponseError("Provider web field is invalid.", provider=self.name)
        rows = web.get("results") or []
        if not isinstance(rows, list):
            raise ProviderResponseError("Provider web.results is not a list.", provider=self.name)

        out: list[SearchResult] = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "") or "")
            url = str(row.get("url", "") or "")
            snippet = str(row.get("description", "") or row.get("snippet", "") or "")
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


def _map_brave_safesearch(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null"}:
        return None
    if v in {"0", "off", "false", "no"}:
        return "off"
    if v in {"1", "moderate", "medium"}:
        return "moderate"
    if v in {"2", "strict", "on", "true", "yes"}:
        return "strict"
    if v in {"off", "moderate", "strict"}:
        return v
    return "moderate"


def _map_brave_freshness(value: str | None) -> str | None:
    """Map time_range to Brave freshness: pd / pw / pm / py."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null", "any", "all"}:
        return None
    aliases = {
        "d": "pd",
        "day": "pd",
        "past_day": "pd",
        "pd": "pd",
        "w": "pw",
        "week": "pw",
        "past_week": "pw",
        "pw": "pw",
        "m": "pm",
        "month": "pm",
        "past_month": "pm",
        "pm": "pm",
        "y": "py",
        "year": "py",
        "past_year": "py",
        "py": "py",
    }
    return aliases.get(v)
