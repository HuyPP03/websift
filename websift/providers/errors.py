"""Search provider error taxonomy.

Messages returned to MCP/callers must be sanitized — never include API keys,
authorization headers, or raw provider response bodies with secrets.
"""

from __future__ import annotations

from typing import Any


class ProviderError(Exception):
    """Base provider failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        provider: str | None = None,
        cause: BaseException | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.provider = provider
        self.cause = cause

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ProviderConfigError(ProviderError):
    """Invalid provider configuration or unsupported request options."""

    def __init__(self, message: str, *, code: str = "config_error", provider: str | None = None, **kw: Any):
        super().__init__(message, code=code, provider=provider, **kw)


class ProviderAuthError(ProviderError):
    """Authentication/authorization failure (401/403)."""

    def __init__(self, message: str = "Provider authentication failed.", *, code: str = "auth_error", **kw: Any):
        super().__init__(message, code=code, **kw)


class ProviderRateLimitError(ProviderError):
    """Rate limited (429); optional retry_after seconds."""

    def __init__(
        self,
        message: str = "Provider rate limited.",
        *,
        retry_after: float | None = None,
        code: str = "rate_limit",
        **kw: Any,
    ):
        super().__init__(message, code=code, **kw)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """Provider call timed out."""

    def __init__(self, message: str = "Provider timed out.", *, code: str = "timeout", **kw: Any):
        super().__init__(message, code=code, **kw)


class ProviderUnavailableError(ProviderError):
    """Provider unreachable or 5xx."""

    def __init__(self, message: str = "Provider unavailable.", *, code: str = "unavailable", **kw: Any):
        super().__init__(message, code=code, **kw)


class ProviderResponseError(ProviderError):
    """Malformed or unexpected provider response."""

    def __init__(self, message: str = "Invalid provider response.", *, code: str = "response_error", **kw: Any):
        super().__init__(message, code=code, **kw)


class ProviderImportError(ProviderError):
    """Optional provider dependency missing."""

    def __init__(self, message: str, *, code: str = "import_error", **kw: Any):
        super().__init__(message, code=code, **kw)


class ProviderBillingError(ProviderError):
    """Insufficient credits, plan limits, or payment required."""

    def __init__(
        self,
        message: str = "Provider billing or plan limit failure.",
        *,
        code: str = "billing_error",
        **kw: Any,
    ):
        super().__init__(message, code=code, **kw)


def sanitize_provider_message(message: str) -> str:
    """Strip likely secrets from a provider error message."""
    from websift.provider_http import redact_secrets

    return redact_secrets(str(message or ""))
