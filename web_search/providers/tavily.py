"""Tavily Search provider — API key required (Authorization Bearer)."""

from __future__ import annotations

from dataclasses import dataclass

from web_search.models import SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.base import ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import ProviderConfigError, ProviderResponseError

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


class TavilyProvider:
    """Tavily Search API (`POST /search`)."""

    name = "tavily"
    capabilities = ProviderCapabilities(
        safe_search=True,
        region=True,
        time_range=True,
        pagination=False,
        domain_filter=False,
    )

    def __init__(self, config: TavilyProviderConfig | None = None, *, http: ProviderHttpClient | None = None):
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
