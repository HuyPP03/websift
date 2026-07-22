"""Search providers package."""

from web_search.providers.base import ProviderCapabilities, SearchProvider, validate_request_capabilities
from web_search.providers.ddgs import DdgsProvider, DdgsProviderConfig
from web_search.providers.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderImportError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from web_search.providers.registry import create_provider, get_default_provider, list_providers

__all__ = [
    "ProviderAuthError",
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
    "create_provider",
    "get_default_provider",
    "list_providers",
    "validate_request_capabilities",
]
