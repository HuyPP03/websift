"""Exa Search provider — API key required (x-api-key)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from web_search.models import ErrorCategory, FetchResult, SearchRequest, SearchResult
from web_search.provider_http import ProviderHttpClient, ProviderHttpConfig
from web_search.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    sanitize_provider_message,
)

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


class ExaProvider(BaseProvider):
    """Exa Search API (`POST /search`) + optional exact-URL contents (`POST /contents`)."""

    name = "exa"
    capabilities = ProviderCapabilities(
        safe_search=False,
        region=False,
        time_range=False,
        pagination=False,
        domain_filter=False,
    )

    def __init__(
        self,
        config: ExaProviderConfig | None = None,
        *,
        http: ProviderHttpClient | None = None,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        super().__init__(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
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

    def fetch(self, url: str) -> FetchResult:
        url = (url or "").strip()
        if not url:
            return FetchResult.failure(url, "No URL provided.", ErrorCategory.EMPTY_INPUT)
        if not self._fetch_context.native_fetch or not (self.config.api_key or "").strip():
            return super().fetch(url)

        blocked = self.validate_url_for_provider(url)
        if blocked is not None:
            return blocked

        try:
            extracted = self._extract_url(url)
        except (ProviderAuthError, ProviderConfigError, ProviderBillingError, ProviderRateLimitError) as e:
            return _fetch_provider_failure(url, e)
        except ProviderError:
            return super().fetch(url)

        if extracted is not None:
            return extracted
        return super().fetch(url)

    def _extract_url(self, url: str) -> FetchResult | None:
        """POST /contents for one URL. Returns success result, or None for URL-level failure."""
        body: dict[str, object] = {
            "urls": [url],
            "text": True,
        }
        payload = self._http.post_json("/contents", json_body=body, provider=self.name)
        if payload is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)
        if not isinstance(payload, dict):
            raise ProviderResponseError("Provider returned non-object JSON.", provider=self.name)

        results = payload.get("results")
        statuses = payload.get("statuses")
        if results is not None and not isinstance(results, list):
            raise ProviderResponseError("Provider results field is not a list.", provider=self.name)
        if statuses is not None and not isinstance(statuses, list):
            raise ProviderResponseError("Provider statuses field is not a list.", provider=self.name)

        for row in results or []:
            if not isinstance(row, dict):
                continue
            row_url = str(row.get("url", "") or row.get("id", "") or "")
            if row_url and not _urls_match(row_url, url) and len(results or []) > 1:
                continue
            content = str(row.get("text", "") or "")
            if content.strip():
                return self.truncate_native_content(
                    url,
                    content,
                    final_url=str(row.get("url", "") or url),
                    content_type="text/plain",
                )

        for st in statuses or []:
            if not isinstance(st, dict):
                continue
            sid = str(st.get("id", "") or st.get("url", "") or "")
            status = str(st.get("status", "") or "").lower()
            if sid and not _urls_match(sid, url) and len(statuses or []) > 1:
                continue
            if status and status not in {"success", "ok", "completed"}:
                return None
            err = st.get("error")
            if isinstance(err, dict) and err:
                return None

        if not results and not statuses:
            raise ProviderResponseError("Provider contents response missing results.", provider=self.name)
        return None


def _urls_match(a: str, b: str) -> bool:
    pa, pb = urlparse(a.strip()), urlparse(b.strip())
    host_a = (pa.hostname or "").lower().lstrip("www.")
    host_b = (pb.hostname or "").lower().lstrip("www.")
    path_a = (pa.path or "/").rstrip("/") or "/"
    path_b = (pb.path or "/").rstrip("/") or "/"
    # Exa may return bare URL without scheme as id.
    if not host_a and a.strip():
        return a.strip().rstrip("/") == b.strip().rstrip("/") or a.strip() in b or b.strip() in a
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
