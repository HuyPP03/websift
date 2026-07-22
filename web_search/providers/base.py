"""Search provider contract and capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from web_search.models import SearchRequest, SearchResult


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider supports; unsupported request filters must not be silently ignored."""

    safe_search: bool = False
    region: bool = False
    time_range: bool = False
    pagination: bool = False
    domain_filter: bool = False


@runtime_checkable
class SearchProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def search(self, request: SearchRequest) -> list[SearchResult]:
        """Execute search and return normalized results.

        Raises provider errors from ``web_search.providers.errors`` on failure.
        """
        ...


def validate_request_capabilities(
    request: SearchRequest,
    capabilities: ProviderCapabilities,
    *,
    allow_unsupported: bool = False,
) -> None:
    """Raise ``ProviderConfigError`` if request uses unsupported filters."""
    from web_search.providers.errors import ProviderConfigError

    if allow_unsupported:
        return
    unsupported: list[str] = []
    if request.safe_search is not None and not capabilities.safe_search:
        unsupported.append("safe_search")
    if request.region is not None and not capabilities.region:
        unsupported.append("region")
    if request.time_range is not None and not capabilities.time_range:
        unsupported.append("time_range")
    if unsupported:
        raise ProviderConfigError(
            f"Provider does not support filter(s): {', '.join(unsupported)}",
            code="unsupported_filter",
        )
