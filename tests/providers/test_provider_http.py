"""Credential isolation for provider HTTP transport vs page fetch."""

from __future__ import annotations

import pytest

from web_search.provider_http import (
    ProviderHttpClient,
    ProviderHttpConfig,
    is_secret_header_name,
    redact_headers,
    redact_secrets,
    validate_provider_base_url,
)
from web_search.providers.errors import ProviderConfigError


class TestRedaction:
    def test_is_secret_header_name(self):
        assert is_secret_header_name("Authorization")
        assert is_secret_header_name("X-API-Key")
        assert is_secret_header_name("x-subscription-token")
        assert is_secret_header_name("Proxy-Authorization")
        assert not is_secret_header_name("Accept")
        assert not is_secret_header_name("X-GitHub-Api-Version")
        assert not is_secret_header_name("Content-Type")

    def test_redact_headers(self):
        out = redact_headers(
            {
                "Authorization": "Bearer supersecret",
                "Accept": "application/json",
                "X-API-Key": "k123",
            }
        )
        assert out["Authorization"] == "[REDACTED]"
        assert out["X-API-Key"] == "[REDACTED]"
        assert out["Accept"] == "application/json"

    def test_redact_secrets_free_text(self):
        text = "failed auth Bearer abcdefghijklmnop and api_key=mysecretvalue"
        red = redact_secrets(text)
        assert "abcdefghijklmnop" not in red
        assert "mysecretvalue" not in red
        assert "[REDACTED]" in red
        assert "Bearer" in red


class TestBaseUrl:
    def test_https_ok(self):
        ok, reason, norm = validate_provider_base_url("https://api.example.com/v1/")
        assert ok is True
        assert reason == ""
        assert norm == "https://api.example.com/v1"

    def test_http_blocked_by_default(self):
        ok, reason, _ = validate_provider_base_url("http://localhost:8080")
        assert ok is False
        assert "https" in reason.lower()

    def test_http_allowed_for_local_dev(self):
        ok, reason, norm = validate_provider_base_url("http://localhost:8080", allow_http=True)
        assert ok is True
        assert norm == "http://localhost:8080"

    def test_userinfo_rejected(self):
        ok, reason, _ = validate_provider_base_url("https://user:pass@api.example.com/")
        assert ok is False
        assert "credential" in reason.lower()

    def test_empty_rejected(self):
        ok, reason, _ = validate_provider_base_url("")
        assert ok is False


class TestProviderHttpClient:
    def test_public_headers_redact_secrets(self):
        client = ProviderHttpClient(
            ProviderHttpConfig(
                base_url="https://api.example.com",
                headers={
                    "Authorization": "Bearer tok_secret_xyz",
                    "Accept": "application/json",
                },
            )
        )
        pub = client.public_headers
        assert pub["Authorization"] == "[REDACTED]"
        assert pub["Accept"] == "application/json"
        # Real headers still available for transport
        built = client.build_headers()
        assert built["Authorization"] == "Bearer tok_secret_xyz"

    def test_invalid_base_url_raises(self):
        with pytest.raises(ProviderConfigError) as ei:
            ProviderHttpClient(ProviderHttpConfig(base_url="ftp://bad.example"))
        assert ei.value.code == "invalid_base_url"

    def test_assert_no_page_fetch_leak_secret_header(self):
        client = ProviderHttpClient(
            ProviderHttpConfig(
                base_url="https://api.example.com",
                headers={"X-API-Key": "secret-key-value"},
            )
        )
        with pytest.raises(ProviderConfigError) as ei:
            client.assert_no_page_fetch_leak({"Authorization": "Bearer x"})
        assert ei.value.code == "credential_isolation"

    def test_assert_no_page_fetch_leak_secret_value(self):
        secret = "super-secret-provider-token"
        client = ProviderHttpClient(
            ProviderHttpConfig(
                base_url="https://api.example.com",
                headers={"X-Subscription-Token": secret},
            )
        )
        with pytest.raises(ProviderConfigError) as ei:
            # Non-secret header name but value equals provider secret
            client.assert_no_page_fetch_leak({"X-Custom": secret})
        assert ei.value.code == "credential_isolation"

    def test_github_non_credential_headers_allowed_on_page_fetch(self):
        """GitHub Accept headers are non-credential and must not be blocked."""
        client = ProviderHttpClient(
            ProviderHttpConfig(
                base_url="https://api.search.example.com",
                headers={"Authorization": "Bearer provider-only"},
            )
        )
        # Same headers used by client GitHub README shortcut
        client.assert_no_page_fetch_leak(
            {
                "Accept": "application/vnd.github.raw+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
