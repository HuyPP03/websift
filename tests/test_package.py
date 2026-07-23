"""Package metadata and public exports."""

from importlib.metadata import PackageNotFoundError, metadata, version

import websift
from websift import AppSettings, WebSearchClient
from websift.config import MAX_PAGE_CHARS
from websift.providers.registry import is_registered, list_providers
from websift.settings import ProviderSettings


def test_version_is_semver_like():
    parts = websift.__version__.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])


def test_version_is_current_release():
    assert websift.__version__ == "1.2.0"


def test_distribution_version_matches_package_when_installed():
    try:
        dist = version("websift")
    except PackageNotFoundError:
        # Editable/source tree without install: skip distribution metadata.
        return
    assert dist == websift.__version__


def test_all_exports_public_api():
    assert "WebSearchClient" in websift.__all__
    assert "AppSettings" in websift.__all__
    assert websift.WebSearchClient is WebSearchClient
    assert websift.AppSettings is AppSettings


def test_client_constructs_with_defaults():
    client = WebSearchClient()
    assert client.max_results == 5
    assert client.timeout == 30
    assert client.max_page_chars == MAX_PAGE_CHARS


def test_client_accepts_custom_kwargs():
    client = WebSearchClient(
        max_results=7,
        search_timeout=11,
        fetch_timeout=22,
        max_page_chars=1000,
        provider="ddgs",
        include_links=False,
        include_images=True,
        output_format="text",
        native_fetch=False,
        safe_search="moderate",
        region="us-en",
        time_range="w",
        allow_unsupported_filters=True,
    )
    assert client.max_results == 7
    assert client.timeout == 11
    assert client._fetch_timeout == 22.0
    assert client.max_page_chars == 1000
    assert client._fetch_context.include_links is False
    assert client._fetch_context.include_images is True
    assert client._fetch_context.output_format == "text"
    assert client._fetch_context.native_fetch is False
    assert getattr(client._provider, "name", None) == "ddgs"
    assert client._settings is not None
    assert client._settings.provider.safe_search == "moderate"
    assert client._settings.provider.region == "us-en"


def test_client_settings_overlay_timeouts():
    settings = AppSettings(provider=ProviderSettings(name="ddgs", max_results=3, timeout_seconds=5))
    client = WebSearchClient(settings=settings, search_timeout=9, fetch_timeout=12, provider="ddgs")
    # settings max_results kept; advanced timeouts overlay
    assert client.max_results == 3
    assert client.timeout == 9
    assert client._fetch_timeout == 12.0


def test_client_api_key_and_base_url_kwargs():
    client = WebSearchClient(
        provider="searxng",
        base_url="https://searx.example",
        api_key="token",
        allow_http=False,
        fallback_providers=["ddgs"],
        max_results=4,
    )
    assert client.max_results == 4
    assert client._settings is not None
    ep = client._settings.provider.endpoint("searxng")
    assert ep.base_url == "https://searx.example"
    assert ep.api_key == "token"
    assert client._settings.provider.fallback_providers == ("ddgs",)


def test_package_doc_mentions_websift():
    doc = (websift.__doc__ or "").lower()
    assert "websift" in doc


def test_optional_provider_extras_declared_when_installed():
    """Optional extras exist for docs/CI; modules ship in the base wheel."""
    try:
        meta = metadata("websift")
    except PackageNotFoundError:
        return
    provides = meta.get_all("Provides-Extra") or []
    for extra in ("mcp", "searxng", "brave", "tavily", "exa", "serper", "providers", "dev"):
        assert extra in provides, provides
    for name in ("ddgs", "searxng", "brave", "tavily", "exa", "serper"):
        assert is_registered(name)
    assert set(list_providers()) >= {"ddgs", "searxng", "brave", "tavily", "exa", "serper"}
