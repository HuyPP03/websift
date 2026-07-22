"""Search providers package."""

from web_search.providers.base import (
    BaseProvider,
    FetchContext,
    ProviderCapabilities,
    SearchProvider,
    process_fetched_body,
    validate_request_capabilities,
)
from web_search.providers.brave import BraveProvider, BraveProviderConfig
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderBillingError,
    ProviderConfigError,
    ProviderError,
    ProviderImportError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from web_search.providers.exa import ExaProvider, ExaProviderConfig
from web_search.providers.fallback import FallbackSearchProvider
from web_search.providers.registry import create_provider, get_default_provider, list_providers
from web_search.providers.searxng import SearxngProvider, SearxngProviderConfig
from web_search.providers.tavily import TavilyProvider, TavilyProviderConfig

__all__ = [
    "BaseProvider",
    "BraveProvider",
    "BraveProviderConfig",
    "ExaProvider",
    "ExaProviderConfig",
    "FallbackSearchProvider",
    "FetchContext",
    "ProviderAuthError",
    "ProviderBillingError",
    "ProviderCapabilities",
    "ProviderConfigError",
    "ProviderError",
    "ProviderImportError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "DdgsProvider",
    "DdgsProviderConfig",
    "SearchProvider",
    "SearxngProvider",
    "SearxngProviderConfig",
    "TavilyProvider",
    "TavilyProviderConfig",
    "create_provider",
    "get_default_provider",
    "list_providers",
    "process_fetched_body",
    "validate_request_capabilities",
]
