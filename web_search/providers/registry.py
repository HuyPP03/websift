"""Allowlisted search provider registry.

Provider selection is server/settings-level only — never from MCP tool arguments.
Factories receive typed config objects; they do not read environment variables.
"""

from __future__ import annotations

from typing import Any, Callable

from web_search.providers.base import SearchProvider
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import ProviderConfigError

ProviderFactory = Callable[[Any], SearchProvider]

# Allowlist only — no dynamic module/class paths from env or MCP.
_REGISTRY: dict[str, ProviderFactory] = {
    "ddgs": lambda cfg: DdgsProvider(cfg if isinstance(cfg, DdgsProviderConfig) else DdgsProviderConfig()),
}


def list_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def is_registered(name: str) -> bool:
    return (name or "").strip().lower() in _REGISTRY


def create_provider(name: str, config: Any = None) -> SearchProvider:
    """Instantiate an allowlisted provider.

    Raises ``ProviderConfigError`` for unknown names (startup validation).
    """
    key = (name or "").strip().lower()
    if not key:
        raise ProviderConfigError("Provider name is required.", code="missing_provider")
    factory = _REGISTRY.get(key)
    if factory is None:
        known = ", ".join(list_providers()) or "(none)"
        raise ProviderConfigError(
            f"Unknown search provider {name!r}. Allowed: {known}",
            code="unknown_provider",
        )
    return factory(config)


def get_default_provider(*, timeout: int = 30) -> SearchProvider:
    return create_provider("ddgs", DdgsProviderConfig(timeout=timeout))
