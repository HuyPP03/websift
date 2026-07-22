"""Exa Search provider — API key required (x-api-key)."""

from __future__ import annotations

from dataclasses import dataclass

from web_search.models import SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.base import ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import ProviderConfigError, ProviderResponseError

_DEFAULT_EXA_BASE = "https://api.exa.ai"


@dataclass(frozen=True)
class ExaProviderConfig:
    api_key: str
    base_url: str = _DEFAULT_EXA_BASE
    timeout: float = 30.0
    allow_http: bool = False
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5


class ExaProvider:
    """Exa Search API (`POST /search`)."""

    name = "exa"
    capabilities = ProviderCapabilities(
        safe_search=False,
        region=False,
        time_range=False,
        pagination=False,
        domain_filter=False,
    )

    def __init__(self, config: ExaProviderConfig | None = None, *, http: ProviderHttpClient | None = None):
        if config is None:
            raise ProviderConfigError("Exa API key is required.", code="missing_api_key", provider="exa")
        key = (config.api_key or "").strip()
        if not key and http is None:
            raise ProviderConfigError("Exa API key is required.", code="missing_api_key", provider=self.name)
        self.config = config
        if http is not None:
            self._http = http
        else:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-api-key": key,
            }
            self._http = ProviderHttpClient(
                ProviderHttpConfig(
                    base_url=config.base_url or _DEFAULT_EXA_BASE,
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
        count = max(1, min(int(request.max_results or 5), 100))
        body: dict[str, object] = {
            "query": request.query,
            "numResults": count,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 1000}},
        }

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
            snippet = str(row.get("text", "") or row.get("snippet", "") or row.get("highlights", "") or "")
            if isinstance(row.get("highlights"), list):
                snippet = " ".join(str(x) for x in row["highlights"] if x)
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
