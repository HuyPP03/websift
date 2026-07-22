"""Typed settings: from_env, validation, no import side-effects."""

from __future__ import annotations

import web_search.settings as settings_mod
from web_search.client import WebSearchClient
from web_search.settings import (
    AppSettings,
    ProviderSettings,
    ServerSettings,
    SettingsError,
)


def test_import_does_not_read_environ(monkeypatch):
    """Importing settings module must not touch os.environ for config."""
    # from_env with empty mapping still works with defaults
    s = AppSettings.from_env({})
    assert s.server.host == "127.0.0.1"
    assert s.server.port == 8787
    assert s.provider.name == "ddgs"
    assert s.provider.timeout_seconds == 30.0
    assert s.fetch.timeout_seconds == 30.0
    assert s.provider.max_results == 5


def test_defaults_without_from_env():
    s = AppSettings()
    assert s.server.host == "127.0.0.1"
    assert s.server.transport == "streamable-http"
    assert s.cache.enabled is False
    s.validate()


def test_search_timeout_alias_maps_both():
    s = AppSettings.from_env({"SEARCH_TIMEOUT": "12"})
    assert s.provider.timeout_seconds == 12.0
    assert s.fetch.timeout_seconds == 12.0


def test_split_timeouts_override_alias():
    s = AppSettings.from_env(
        {
            "SEARCH_TIMEOUT": "99",
            "SEARCH_TIMEOUT_SECONDS": "7",
            "FETCH_TIMEOUT_SECONDS": "9",
        }
    )
    assert s.provider.timeout_seconds == 7.0
    assert s.fetch.timeout_seconds == 9.0


def test_legacy_alias_fills_missing_side_only():
    s = AppSettings.from_env(
        {
            "SEARCH_TIMEOUT": "15",
            "SEARCH_TIMEOUT_SECONDS": "4",
        }
    )
    assert s.provider.timeout_seconds == 4.0
    assert s.fetch.timeout_seconds == 15.0


def test_mcp_host_port_transport():
    s = AppSettings.from_env(
        {
            "MCP_HOST": "0.0.0.0",
            "MCP_PORT": "9001",
            "MCP_TRANSPORT": "stdio",
            "SEARCH_MAX_RESULTS": "8",
            "SEARCH_PROVIDER": "ddgs",
        }
    )
    assert s.server.host == "0.0.0.0"
    assert s.server.port == 9001
    assert s.server.transport == "stdio"
    assert s.provider.max_results == 8


def test_invalid_port():
    try:
        AppSettings.from_env({"MCP_PORT": "0"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "out_of_range" or "port" in e.message.lower() or e.code == "invalid_port"
    assert raised


def test_invalid_transport():
    try:
        AppSettings.from_env({"MCP_TRANSPORT": "websocket"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "invalid_transport"
    assert raised


def test_invalid_int():
    try:
        AppSettings.from_env({"SEARCH_MAX_RESULTS": "nope"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "invalid_int"
        assert "nope" in e.message or "SEARCH_MAX_RESULTS" in e.message
    assert raised


def test_unknown_provider_fail_fast():
    try:
        AppSettings.from_env({"SEARCH_PROVIDER": "not-real"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "unknown_provider"
        assert "ddgs" in e.message
        # no secret leakage concern
    assert raised


def test_with_overrides_provider_section():
    base = AppSettings()
    next_s = base.with_overrides(provider=ProviderSettings(name="ddgs", max_results=9, timeout_seconds=3))
    assert next_s.provider.max_results == 9
    assert next_s.provider.timeout_seconds == 3
    assert base.provider.max_results == 5  # immutable


def test_with_overrides_unknown_section():
    try:
        AppSettings().with_overrides(not_a_section=ServerSettings())
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "unknown_section"
    assert raised


def test_bool_parsing():
    s = AppSettings.from_env(
        {
            "CACHE_ENABLED": "true",
            "SEARCH_ALLOW_UNSUPPORTED_FILTERS": "1",
            "HTML_INCLUDE_LINKS": "off",
        }
    )
    assert s.cache.enabled is True
    assert s.provider.allow_unsupported_filters is True
    assert s.extraction.include_links is False


def test_invalid_bool():
    try:
        AppSettings.from_env({"CACHE_ENABLED": "maybe"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "invalid_bool"
    assert raised


def test_bearer_requires_token():
    try:
        AppSettings.from_env({"MCP_AUTH_MODE": "bearer"})
        raised = False
    except SettingsError as e:
        raised = True
        assert e.code == "missing_bearer_token"
    assert raised


def test_bearer_ok_with_token():
    s = AppSettings.from_env({"MCP_AUTH_MODE": "bearer", "MCP_BEARER_TOKEN": "secret-token"})
    assert s.auth.mode == "bearer"
    assert s.auth.bearer_token == "secret-token"
    # repr redacts
    assert "secret-token" not in repr(s.auth)


def test_client_from_settings_split_timeouts():
    s = AppSettings.from_env(
        {
            "SEARCH_TIMEOUT_SECONDS": "5",
            "FETCH_TIMEOUT_SECONDS": "11",
            "SEARCH_MAX_RESULTS": "2",
            "PAGE_MAX_CHARS": "1000",
        }
    )
    client = WebSearchClient(settings=s)
    assert client.max_results == 2
    assert client.timeout == 5
    assert client._search_timeout == 5.0
    assert client._fetch_timeout == 11.0
    assert client.max_page_chars == 1000
    assert client._provider.name == "ddgs"


def test_client_legacy_kwargs_still_work():
    client = WebSearchClient(max_results=4, timeout=9, max_page_chars=500)
    assert client.max_results == 4
    assert client.timeout == 9
    assert client._search_timeout == 9.0
    assert client._fetch_timeout == 9.0
    assert client.max_page_chars == 500


def test_provider_api_key_repr_redacted():
    p = ProviderSettings(name="brave", api_key="super-secret-key")
    assert "super-secret-key" not in repr(p)


def test_settings_module_has_no_cached_env_settings():
    # Characterization: no module-level AppSettings.from_env() result
    assert not hasattr(settings_mod, "SETTINGS")
    assert not hasattr(settings_mod, "settings")
