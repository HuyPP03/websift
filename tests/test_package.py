"""Package metadata and public exports."""

import web_search
from web_search import WebSearchClient


def test_version_is_semver_like():
    parts = web_search.__version__.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])


def test_version_matches_expected_baseline():
    # Characterization: current released alpha.
    assert web_search.__version__ == "0.1.0"


def test_all_exports_websearchclient():
    assert "WebSearchClient" in web_search.__all__
    assert web_search.WebSearchClient is WebSearchClient


def test_client_constructs_with_defaults():
    client = WebSearchClient()
    assert client.max_results == 5
    assert client.timeout == 30
    assert client.max_page_chars == 32_000
