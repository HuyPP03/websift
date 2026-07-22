"""Opt-in multi-provider fallback chain."""

from __future__ import annotations

from web_search.models import SearchRequest, SearchResult
from web_search.providers.base import ProviderCapabilities, SearchProvider
from web_search.providers.errors import ProviderAuthError, ProviderConfigError, ProviderError


class FallbackSearchProvider:
    """Try primary then configured fallbacks.

    Does **not** fall back on config/auth errors (fail fast).
    Falls back on timeout / rate-limit / unavailable / response / import errors.
    """

    def __init__(self, providers: list[SearchProvider]):
        if not providers:
            raise ProviderConfigError("Fallback chain requires at least one provider.", code="empty_fallback_chain")
        self._providers = list(providers)
        self.name = self._providers[0].name
        self.capabilities = getattr(self._providers[0], "capabilities", ProviderCapabilities())

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
