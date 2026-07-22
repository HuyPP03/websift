"""Package metadata and public exports."""

from importlib.metadata import PackageNotFoundError, metadata, version

import web_search
from web_search import WebSearchClient
from web_search.providers.registry import is_registered, list_providers


def test_version_is_semver_like():
    parts = web_search.__version__.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])


def test_version_is_providers_release():
    assert web_search.__version__ == "0.3.0"


def test_distribution_version_matches_package_when_installed():
    try:
        dist = version("websift")
    except PackageNotFoundError:
        # Editable/source tree without install: skip distribution metadata.
        return
    assert dist == web_search.__version__


def test_all_exports_websearchclient():
    assert "WebSearchClient" in web_search.__all__
    assert web_search.WebSearchClient is WebSearchClient


def test_client_constructs_with_defaults():
    client = WebSearchClient()
    assert client.max_results == 5
    assert client.timeout == 30
    assert client.max_page_chars == 32_000


def test_dual_naming_documented_in_package_doc():
    doc = (web_search.__doc__ or "").lower()
    assert "websift" in doc
    assert "web_search" in doc


def test_optional_provider_extras_declared_when_installed():
    """Optional extras exist for docs/CI; modules ship in the base wheel."""
    try:
        meta = metadata("websift")
    except PackageNotFoundError:
        return
    provides = meta.get_all("Provides-Extra") or []
    for extra in ("searxng", "brave", "tavily", "exa", "providers", "dev"):
        assert extra in provides, provides
    for name in ("ddgs", "searxng", "brave", "tavily", "exa"):
        assert is_registered(name)
    assert set(list_providers()) >= {"ddgs", "searxng", "brave", "tavily", "exa"}
