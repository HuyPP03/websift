"""Serper search provider — Google SERP via google.serper.dev (stdlib HTTP)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from websift.models import SearchRequest, SearchResult
from websift.provider_http import ProviderHttpClient, ProviderHttpConfig
from websift.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from websift.providers.errors import ProviderConfigError, ProviderResponseError

_DEFAULT_SERPER_BASE = "https://google.serper.dev"


@dataclass(frozen=True)
class SerperProviderConfig:
    api_key: str
    base_url: str = _DEFAULT_SERPER_BASE
    timeout: float = 30.0
    allow_http: bool = False
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5


class SerperProvider(BaseProvider):
    """Serper Web Search API (``POST /search``)."""

    name = "serper"
    capabilities = ProviderCapabilities(
        safe_search=False,
        region=True,
        time_range=True,
        pagination=False,
        domain_filter=False,
    )

    def __init__(
        self,
        config: SerperProviderConfig | None = None,
        *,
        http: ProviderHttpClient | None = None,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        super().__init__(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
        if config is None:
            raise ProviderConfigError("Serper API key is required.", code="missing_api_key", provider="serper")
        key = (config.api_key or "").strip()
        if not key and http is None:
            raise ProviderConfigError("Serper API key is required.", code="missing_api_key", provider=self.name)
        self.config = config
        if http is not None:
            self._http = http
        else:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "X-API-KEY": key,
                "Content-Type": "application/json",
            }
            self._http = ProviderHttpClient(
                ProviderHttpConfig(
                    base_url=config.base_url or _DEFAULT_SERPER_BASE,
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
        body: dict[str, object] = {"q": request.query, "num": count}
        if request.region:
            # Serper uses ISO country codes (e.g. us, gb).
            body["gl"] = str(request.region).strip().lower()
        tbs = _map_serper_tbs(request.time_range)
        if tbs is not None:
            body["tbs"] = tbs

        payload = self._http.post_json("/search", json_body=body, provider=self.name)
        if payload is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)
        if not isinstance(payload, dict):
            raise ProviderResponseError("Provider returned non-object JSON.", provider=self.name)

        rows = payload.get("organic") or []
        if not isinstance(rows, list):
            raise ProviderResponseError("Provider organic field is not a list.", provider=self.name)

        out: list[SearchResult] = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "") or "")
            url = str(row.get("link", "") or row.get("url", "") or "")
            snippet = str(row.get("snippet", "") or row.get("description", "") or "")
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


def _map_serper_tbs(value: str | None) -> str | None:
    """Map time_range aliases to Google ``tbs`` freshness tokens."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"", "none", "null", "any", "all"}:
        return None
    aliases = {
        "d": "qdr:d",
        "day": "qdr:d",
        "past_day": "qdr:d",
        "qdr:d": "qdr:d",
        "w": "qdr:w",
        "week": "qdr:w",
        "past_week": "qdr:w",
        "qdr:w": "qdr:w",
        "m": "qdr:m",
        "month": "qdr:m",
        "past_month": "qdr:m",
        "qdr:m": "qdr:m",
        "y": "qdr:y",
        "year": "qdr:y",
        "past_year": "qdr:y",
        "qdr:y": "qdr:y",
    }
    return aliases.get(v)
