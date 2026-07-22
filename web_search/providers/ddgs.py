"""DDGS (DuckDuckGo) search provider — default, no API key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_search.models import SearchRequest, SearchResult
from web_search.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from web_search.providers.errors import (
    ProviderError,
    ProviderImportError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    sanitize_provider_message,
)


@dataclass(frozen=True)
class DdgsProviderConfig:
    timeout: int = 30
    allow_unsupported_filters: bool = False


class DdgsProvider(BaseProvider):
    """DuckDuckGo search via the ``ddgs`` package."""

    name = "ddgs"
    capabilities = ProviderCapabilities(
        safe_search=False,
        region=False,
        time_range=False,
        pagination=False,
        domain_filter=False,
    )

    def __init__(
        self,
        config: DdgsProviderConfig | None = None,
        *,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        super().__init__(fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
        self.config = config or DdgsProviderConfig()

    def search(self, request: SearchRequest) -> list[SearchResult]:
        validate_request_capabilities(
            request,
            self.capabilities,
            allow_unsupported=self.config.allow_unsupported_filters,
        )
        try:
            from ddgs import DDGS
        except ImportError as e:
            raise ProviderImportError(
                "Error: ddgs not installed. Run: pip install ddgs",
                provider=self.name,
                cause=e,
            ) from e

        try:
            raw = DDGS(timeout=self.config.timeout).text(
                request.query,
                max_results=request.max_results,
            )
        except Exception as e:
            raise _map_ddgs_exception(e, provider=self.name) from e

        if raw is None:
            raise ProviderResponseError("Provider returned no payload.", provider=self.name)

        results: list[SearchResult] = []
        if not raw:
            return results

        for i, row in enumerate(raw, start=1):
            if not isinstance(row, dict):
                continue
            results.append(
                SearchResult(
                    title=str(row.get("title", "") or ""),
                    url=str(row.get("href", "") or ""),
                    snippet=str(row.get("body", "") or ""),
                    rank=i,
                    source=self.name,
                )
            )
        return results


def _map_ddgs_exception(exc: BaseException, *, provider: str) -> ProviderError:
    msg = sanitize_provider_message(str(exc))
    name = type(exc).__name__.lower()
    text = msg.lower()
    if "timeout" in text or "timed out" in text or "timeout" in name:
        return ProviderTimeoutError(f"Search failed: {msg}", provider=provider, cause=exc)
    if "rate" in text or "429" in text or "limit" in text:
        from web_search.providers.errors import ProviderRateLimitError

        return ProviderRateLimitError(f"Search failed: {msg}", provider=provider, cause=exc)
    if isinstance(exc, (ConnectionError, OSError)) or "connection" in text:
        return ProviderUnavailableError(f"Search failed: {msg}", provider=provider, cause=exc)
    return ProviderUnavailableError(f"Search failed: {msg}", provider=provider, cause=exc)
