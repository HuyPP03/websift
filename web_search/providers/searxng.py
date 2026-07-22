"""SearXNG search provider — self-hosted, optional auth header."""

from __future__ import annotations

from dataclasses import dataclass

from web_search.models import SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.base import ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import ProviderConfigError, ProviderResponseError


@dataclass(frozen=True)
class SearxngProviderConfig:
    base_url: str
    api_key: str | None = None
    timeout: float = 30.0
    allow_http: bool = False
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5
    # Header name for deployments that expect a custom key (default Authorization Bearer).
    auth_header: str = "Authorization"


class SearxngProvider:
    """SearXNG JSON search API (`/search?format=json`)."""

    name = "searxng"
    capabilities = ProviderCapabilities(
        safe_search=True,
        region=True,
        time_range=False,
        pagination=True,
        domain_filter=False,
    )

    def __init__(self, config: SearxngProviderConfig | None = None, *, http: ProviderHttpClient | None = None):
        if config is None and http is None:
            raise ProviderConfigError("SearXNG base_url is required.", code="missing_base_url", provider="searxng")
        self.config = config or SearxngProviderConfig(base_url=http.base_url if http else "")
        if not (self.config.base_url or "").strip() and http is None:
            raise ProviderConfigError("SearXNG base_url is required.", code="missing_base_url", provider=self.name)
        if http is not None:
            self._http = http
        else:
            headers: dict[str, str] = {"Accept": "application/json"}
            key = (self.config.api_key or "").strip()
            if key:
                header = (self.config.auth_header or "Authorization").strip() or "Authorization"
                if header.lower() == "authorization" and not key.lower().startswith("bearer "):
                    headers[header] = f"Bearer {key}"
                else:
                    headers[header] = key
            self._http = ProviderHttpClient(
                ProviderHttpConfig(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    headers=headers,
                    allow_http=self.config.allow_http,
                    retry_max=self.config.retry_max,
                    retry_backoff_seconds=self.config.retry_backoff_seconds,
                )
            )

    def search(self, request: SearchRequest) -> list[SearchResult]:
        validate_request_capabilities(
            request,
            self.capabilities,
            allow_unsupported=self.config.allow_unsupported_filters,
        )
        params: dict[str, object] = {
            "q": request.query,
            "format": "json",
            "pageno": 1,
        }
        if request.max_results:
            # SearXNG does not always honor count; still pass a hint some instances use.
            params["number_of_results"] = int(request.max_results)
        safesearch = _map_safesearch(request.safe_search)
        if safesearch is not None:
            params["safesearch"] = safesearch
        if request.region:
            params["language"] = request.region

        payload = self._http.get_json("/search", params=params, provider=self.name)
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
            url = str(row.get("url", "") or row.get("href", "") or "")
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
            if request.max_results and len(out) >= int(request.max_results):
                break
        return out


def _map_safesearch(value: str | None) -> int | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null"}:
        return None
    if v in {"0", "off", "false", "no"}:
        return 0
    if v in {"1", "moderate", "medium"}:
        return 1
    if v in {"2", "strict", "on", "true", "yes"}:
        return 2
    # Pass through numeric-looking strings when possible.
    if v.isdigit():
        return max(0, min(2, int(v)))
    return 1
