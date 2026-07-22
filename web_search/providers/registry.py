"""Allowlisted search provider registry.

Provider selection is server/settings-level only — never from MCP tool arguments.
Factories receive typed config objects; they do not read environment variables.
"""

from __future__ import annotations

from typing import Any, Callable

from web_search.providers.base import SearchProvider
from web_search.providers.brave import BraveProvider, BraveProviderConfig
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import ProviderConfigError
from web_search.providers.exa import ExaProvider, ExaProviderConfig
from web_search.providers.searxng import SearxngProvider, SearxngProviderConfig
from web_search.providers.tavily import TavilyProvider, TavilyProviderConfig

ProviderFactory = Callable[[Any], SearchProvider]


def _make_ddgs(cfg: Any) -> SearchProvider:
    return DdgsProvider(cfg if isinstance(cfg, DdgsProviderConfig) else DdgsProviderConfig())


def _make_searxng(cfg: Any) -> SearchProvider:
    if isinstance(cfg, SearxngProviderConfig):
        return SearxngProvider(cfg)
    if isinstance(cfg, dict):
        return SearxngProvider(SearxngProviderConfig(**cfg))
    raise ProviderConfigError(
        "SearXNG requires SearxngProviderConfig (base_url).",
        code="missing_config",
        provider="searxng",
    )


def _make_brave(cfg: Any) -> SearchProvider:
    if isinstance(cfg, BraveProviderConfig):
        return BraveProvider(cfg)
    if isinstance(cfg, dict):
        return BraveProvider(BraveProviderConfig(**cfg))
    raise ProviderConfigError(
        "Brave requires BraveProviderConfig (api_key).",
        code="missing_config",
        provider="brave",
    )


def _make_tavily(cfg: Any) -> SearchProvider:
    if isinstance(cfg, TavilyProviderConfig):
        return TavilyProvider(cfg)
    if isinstance(cfg, dict):
        return TavilyProvider(TavilyProviderConfig(**cfg))
    raise ProviderConfigError(
        "Tavily requires TavilyProviderConfig (api_key).",
        code="missing_config",
        provider="tavily",
    )


def _make_exa(cfg: Any) -> SearchProvider:
    if isinstance(cfg, ExaProviderConfig):
        return ExaProvider(cfg)
    if isinstance(cfg, dict):
        return ExaProvider(ExaProviderConfig(**cfg))
    raise ProviderConfigError(
        "Exa requires ExaProviderConfig (api_key).",
        code="missing_config",
        provider="exa",
    )


# Allowlist only — no dynamic module/class paths from env or MCP.
_REGISTRY: dict[str, ProviderFactory] = {
    "ddgs": _make_ddgs,
    "searxng": _make_searxng,
    "brave": _make_brave,
    "tavily": _make_tavily,
    "exa": _make_exa,
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
