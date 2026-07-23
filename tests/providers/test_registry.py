"""Allowlisted provider registry."""

from __future__ import annotations

import pytest

from websift.providers.ddgs import DdgsProvider, DdgsProviderConfig
from websift.providers.errors import ProviderConfigError
from websift.providers.registry import (
    create_provider,
    get_default_provider,
    is_registered,
    list_providers,
)


def test_list_providers_includes_builtin_p1():
    names = list_providers()
    assert "ddgs" in names
    assert "searxng" in names
    assert "brave" in names
    assert "tavily" in names
    assert "exa" in names
    assert "serper" in names
    assert names == tuple(sorted(names))


def test_is_registered_case_insensitive():
    assert is_registered("ddgs")
    assert is_registered("DDGS")
    assert is_registered(" Ddgs ")
    assert is_registered("brave")
    assert is_registered("SEARXNG")
    assert is_registered("tavily")
    assert is_registered("EXA")
    assert is_registered("serper")
    assert is_registered("SERPER")
    assert not is_registered("serpapi")
    assert not is_registered("")
    assert not is_registered("  ")


def test_create_provider_ddgs_default_config():
    p = create_provider("ddgs")
    assert isinstance(p, DdgsProvider)
    assert p.name == "ddgs"
    assert p.config.timeout == 30


def test_create_provider_ddgs_typed_config():
    p = create_provider("ddgs", DdgsProviderConfig(timeout=12))
    assert isinstance(p, DdgsProvider)
    assert p.config.timeout == 12


def test_create_provider_unknown_raises():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("not-a-provider")
    assert ei.value.code == "unknown_provider"
    assert "ddgs" in ei.value.message


def test_create_provider_empty_name():
    with pytest.raises(ProviderConfigError) as ei:
        create_provider("")
    assert ei.value.code == "missing_provider"


def test_get_default_provider_timeout():
    p = get_default_provider(timeout=7)
    assert isinstance(p, DdgsProvider)
    assert p.config.timeout == 7
