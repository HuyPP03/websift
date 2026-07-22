"""Allowlisted search provider registry.

Provider selection is server/settings-level only — never from MCP tool arguments.
Factories receive typed config objects; they do not read environment variables.
"""

from __future__ import annotations

from typing import Any, Callable

from web_search.providers.base import FetchContext, SearchProvider
from web_search.providers.brave import BraveProvider, BraveProviderConfig
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import ProviderConfigError
from web_search.providers.exa import ExaProvider, ExaProviderConfig
from web_search.providers.searxng import SearxngProvider, SearxngProviderConfig
from web_search.providers.tavily import TavilyProvider, TavilyProviderConfig

ProviderFactory = Callable[..., SearchProvider]


def _make_ddgs(
    cfg: Any,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    return DdgsProvider(
        cfg if isinstance(cfg, DdgsProviderConfig) else DdgsProviderConfig(),
        fetch_context=fetch_context,
        pdf_semaphore=pdf_semaphore,
    )


def _make_searxng(
    cfg: Any,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    if isinstance(cfg, SearxngProviderConfig):
        return SearxngProvider(cfg, fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
    if isinstance(cfg, dict):
        return SearxngProvider(
            SearxngProviderConfig(**cfg),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )
    raise ProviderConfigError(
        "SearXNG requires SearxngProviderConfig (base_url).",
        code="missing_config",
        provider="searxng",
    )


def _make_brave(
    cfg: Any,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    if isinstance(cfg, BraveProviderConfig):
        return BraveProvider(cfg, fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
    if isinstance(cfg, dict):
        return BraveProvider(
            BraveProviderConfig(**cfg),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )
    raise ProviderConfigError(
        "Brave requires BraveProviderConfig (api_key).",
        code="missing_config",
        provider="brave",
    )


def _make_tavily(
    cfg: Any,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    if isinstance(cfg, TavilyProviderConfig):
        return TavilyProvider(cfg, fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
    if isinstance(cfg, dict):
        return TavilyProvider(
            TavilyProviderConfig(**cfg),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )
    raise ProviderConfigError(
        "Tavily requires TavilyProviderConfig (api_key).",
        code="missing_config",
        provider="tavily",
    )


def _make_exa(
    cfg: Any,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    if isinstance(cfg, ExaProviderConfig):
        return ExaProvider(cfg, fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)
    if isinstance(cfg, dict):
        return ExaProvider(
            ExaProviderConfig(**cfg),
            fetch_context=fetch_context,
            pdf_semaphore=pdf_semaphore,
        )
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


def create_provider(
    name: str,
    config: Any = None,
    *,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
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
    return factory(config, fetch_context=fetch_context, pdf_semaphore=pdf_semaphore)


def get_default_provider(
    *,
    timeout: int = 30,
    fetch_context: FetchContext | None = None,
    pdf_semaphore: Any = None,
) -> SearchProvider:
    return create_provider(
        "ddgs",
        DdgsProviderConfig(timeout=timeout),
        fetch_context=fetch_context,
        pdf_semaphore=pdf_semaphore,
    )
