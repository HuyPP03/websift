"""DDGS (DuckDuckGo) search provider — default, no API key."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from websift.models import SearchRequest, SearchResult
from websift.providers.base import BaseProvider, FetchContext, ProviderCapabilities, validate_request_capabilities
from websift.providers.errors import (
    ProviderError,
    ProviderImportError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    sanitize_provider_message,
)


@dataclass(frozen=True)
class DdgsProviderConfig:
    timeout: int = 30
    allow_unsupported_filters: bool = False
    retry_max: int = 1
    retry_backoff_seconds: float = 0.5


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

        attempts = max(0, int(self.config.retry_max)) + 1
        raw: Any = None
        last_error: ProviderError | None = None
        for attempt in range(attempts):
            try:
                raw = DDGS(timeout=self.config.timeout).text(
                    request.query,
                    max_results=request.max_results,
                )
                last_error = None
                break
            except Exception as e:
                mapped = _map_ddgs_exception(e, provider=self.name)
                last_error = mapped
                if attempt + 1 >= attempts or not _is_retryable(mapped):
                    raise mapped from e
                delay = float(self.config.retry_backoff_seconds) * (2**attempt)
                if delay > 0:
                    time.sleep(min(delay, 5.0))

        if last_error is not None:
            raise last_error

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


def _is_retryable(err: ProviderError) -> bool:
    return isinstance(err, (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError))


def _map_ddgs_exception(exc: BaseException, *, provider: str) -> ProviderError:
    msg = sanitize_provider_message(str(exc))
    name = type(exc).__name__.lower()
    text = msg.lower()
    if "timeout" in text or "timed out" in text or "timeout" in name:
        return ProviderTimeoutError(
            "Search failed: DuckDuckGo request timed out. "
            "Retry later or increase SEARCH_TIMEOUT_SECONDS / search_timeout.",
            provider=provider,
            cause=exc,
        )
    if (
        "rate" in text
        or "429" in text
        or "limit" in text
        or "blocked" in text
        or "captcha" in text
        or "forbidden" in text
    ):
        return ProviderRateLimitError(
            "Search failed: DuckDuckGo rate-limited or blocked this client. "
            "Wait and retry, lower SEARCH_MAX_CONCURRENCY, or switch SEARCH_PROVIDER.",
            provider=provider,
            cause=exc,
        )
    if isinstance(exc, (ConnectionError, OSError)) or "connection" in text:
        return ProviderUnavailableError(
            "Search failed: could not reach DuckDuckGo. Check network connectivity.",
            provider=provider,
            cause=exc,
        )
    detail = msg if msg else type(exc).__name__
    return ProviderUnavailableError(
        f"Search failed: DuckDuckGo provider error ({detail}).",
        provider=provider,
        cause=exc,
    )
