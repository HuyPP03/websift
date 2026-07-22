"""Provider HTTP transport (credential-aware) — separate from page-fetch SSRF path.

Arbitrary ``fetch_raw`` / ``web_fetch`` must never use this module's secret headers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlparse

_SECRET_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "x-subscription-token",
        "x-auth-token",
    }
)
_SECRET_KEY_HINTS = (
    "authorization",
    "api_key",
    "apikey",
    "api-key",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "subscription",
)
_REDACTED = "[REDACTED]"
# Bearer tokens, long hex/base64-looking secrets in free text.
_TOKEN_RE = re.compile(
    r"(?i)\b(bearer\s+)[a-z0-9._\-+/=]{8,}\b"
    r"|(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^\s'\",;]+)"
)


def is_secret_header_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if n in _SECRET_HEADER_NAMES:
        return True
    return any(h in n for h in ("token", "secret", "password", "api-key", "apikey"))


def redact_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Return a copy of headers with secret values redacted (for logs/errors)."""
    if not headers:
        return {}
    out: dict[str, str] = {}
    for k, v in headers.items():
        out[str(k)] = _REDACTED if is_secret_header_name(str(k)) else str(v)
    return out


def redact_secrets(text: str) -> str:
    """Best-effort redaction of secrets in free-form error/log text."""
    if not text:
        return ""
    s = str(text)
    s = _TOKEN_RE.sub(
        lambda m: (m.group(1) or "") + _REDACTED
        if m.group(1)
        else f"{m.group(2)}={_REDACTED}",
        s,
    )
    # Query-string style key=value for common secret names.
    for hint in _SECRET_KEY_HINTS:
        s = re.sub(
            rf"(?i)({re.escape(hint)}\s*[=:]\s*)([^\s&,;]+)",
            rf"\1{_REDACTED}",
            s,
        )
    return s


def validate_provider_base_url(
    url: str,
    *,
    allow_http: bool = False,
) -> tuple[bool, str, str]:
    """Validate a configured provider base URL (not MCP caller input).

    Returns ``(ok, reason, normalized_url)``.
    """
    raw = (url or "").strip()
    if not raw:
        return False, "Provider base_url is required.", ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False, "Provider base_url must be http or https.", ""
    if parsed.scheme == "http" and not allow_http:
        return False, "Provider base_url must use https (set allow_http for local dev).", ""
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        return False, "Provider base_url must not contain embedded credentials.", ""
    if not parsed.hostname:
        return False, "Provider base_url must include a hostname.", ""
    # Normalize: strip fragment; keep path.
    normalized = parsed._replace(fragment="").geturl()
    return True, "", normalized.rstrip("/")


@dataclass
class ProviderHttpConfig:
    """Typed config for provider HTTP calls (never mixed into page fetch)."""

    base_url: str
    timeout: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)
    allow_http: bool = False


class ProviderHttpClient:
    """Minimal credential-aware HTTP helper for search providers.

    Intentionally separate from ``web_search.http.fetch_raw`` so API keys never
    ride on the arbitrary page-fetch path.
    """

    def __init__(self, config: ProviderHttpConfig):
        ok, reason, base = validate_provider_base_url(config.base_url, allow_http=config.allow_http)
        if not ok:
            from web_search.providers.errors import ProviderConfigError

            raise ProviderConfigError(reason, code="invalid_base_url")
        self.base_url = base
        self.timeout = config.timeout
        self._headers = dict(config.headers or {})

    @property
    def public_headers(self) -> dict[str, str]:
        """Headers safe for logging (secrets redacted)."""
        return redact_headers(self._headers)

    def build_headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = dict(self._headers)
        if extra:
            headers.update(extra)
        return headers

    def assert_no_page_fetch_leak(self, page_fetch_headers: Mapping[str, str] | None) -> None:
        """Raise if any secret header appears on a page-fetch header map."""
        if not page_fetch_headers:
            return
        for name, value in page_fetch_headers.items():
            if is_secret_header_name(str(name)):
                from web_search.providers.errors import ProviderConfigError

                raise ProviderConfigError(
                    f"Refusing to attach secret header {name!r} to page fetch.",
                    code="credential_isolation",
                )
            # Also refuse values that equal known secret values from this client.
            for secret in self._headers.values():
                if secret and str(value) == str(secret):
                    from web_search.providers.errors import ProviderConfigError

                    raise ProviderConfigError(
                        "Refusing to attach provider secret value to page fetch.",
                        code="credential_isolation",
                    )
