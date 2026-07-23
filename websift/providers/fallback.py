"""Opt-in multi-provider fallback chain."""

from __future__ import annotations

from typing import Any

from websift.models import FetchResult, SearchRequest, SearchResult
from websift.providers.base import BaseProvider, FetchContext, ProviderCapabilities, SearchProvider
from websift.providers.errors import ProviderAuthError, ProviderConfigError, ProviderError


class FallbackSearchProvider(BaseProvider):
    """Try primary then configured fallbacks for **search** only.

    ``fetch`` always uses the primary provider (no multi-vendor extract chain).
    Does **not** fall back search on config/auth errors (fail fast).
    Falls back search on timeout / rate-limit / unavailable / response / import errors.
    """

    def __init__(
        self,
        providers: list[SearchProvider],
        *,
        fetch_context: FetchContext | None = None,
        pdf_semaphore: Any = None,
    ):
        if not providers:
            raise ProviderConfigError("Fallback chain requires at least one provider.", code="empty_fallback_chain")
        self._providers = list(providers)
        primary = self._providers[0]
        # Prefer primary's fetch context when not explicitly provided.
        ctx = fetch_context
        if ctx is None and isinstance(primary, BaseProvider):
            ctx = primary._fetch_context
        sem = pdf_semaphore
        if sem is None and isinstance(primary, BaseProvider):
            sem = primary._pdf_semaphore
        super().__init__(fetch_context=ctx, pdf_semaphore=sem)
        self.name = primary.name
        self.capabilities = getattr(primary, "capabilities", ProviderCapabilities())

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return tuple(self._providers)

    def search(self, request: SearchRequest) -> list[SearchResult]:
        last_error: ProviderError | None = None
        for provider in self._providers:
            try:
                return provider.search(request)
            except (ProviderConfigError, ProviderAuthError):
                # Config/auth are operator mistakes — do not mask with another provider.
                raise
            except ProviderError as e:
                last_error = e
                continue
        assert last_error is not None
        raise last_error

    def fetch(self, url: str) -> FetchResult:
        """Exact-URL fetch uses primary only — never the search fallback chain."""
        primary = self._providers[0]
        return primary.fetch(url)
