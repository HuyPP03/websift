"""Provider contract helpers and capabilities validation."""

from __future__ import annotations

import pytest

from websift.models import SearchRequest
from websift.providers.base import ProviderCapabilities, validate_request_capabilities
from websift.providers.errors import ProviderConfigError


def test_validate_ok_when_no_filters():
    req = SearchRequest(query="q", max_results=5)
    caps = ProviderCapabilities()
    validate_request_capabilities(req, caps)  # no raise


def test_validate_rejects_unsupported_filters():
    req = SearchRequest(
        query="q",
        max_results=5,
        safe_search="moderate",
        region="us-en",
        time_range="w",
    )
    caps = ProviderCapabilities(safe_search=False, region=False, time_range=False)
    with pytest.raises(ProviderConfigError) as ei:
        validate_request_capabilities(req, caps)
    assert ei.value.code == "unsupported_filter"
    assert "safe_search" in ei.value.message
    assert "region" in ei.value.message
    assert "time_range" in ei.value.message


def test_validate_allows_supported_filters():
    req = SearchRequest(query="q", max_results=5, safe_search="off", region="wt-wt")
    caps = ProviderCapabilities(safe_search=True, region=True)
    validate_request_capabilities(req, caps)


def test_validate_allow_unsupported_skips():
    req = SearchRequest(query="q", max_results=5, safe_search="strict")
    caps = ProviderCapabilities(safe_search=False)
    validate_request_capabilities(req, caps, allow_unsupported=True)
