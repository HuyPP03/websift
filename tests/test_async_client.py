"""Async WebSearchClient.asearch / afetch."""

from __future__ import annotations

import pytest

from websift.client import WebSearchClient
from websift.models import FetchResult, SearchResult


class _FakeProvider:
    name = "fake"

    def search(self, request):
        return [
            SearchResult(
                title="Async Title",
                url="https://example.com/a",
                snippet="snippet",
                rank=1,
                source="fake",
            )
        ]

    def fetch(self, url: str):
        return FetchResult.success(url, f"body:{url}", final_url=url, status_code=200)


@pytest.mark.asyncio
async def test_asearch_matches_search():
    client = WebSearchClient(provider=_FakeProvider())
    sync_out = client.search("hello")
    async_out = await client.asearch("hello")
    assert async_out == sync_out
    assert "Async Title" in async_out


@pytest.mark.asyncio
async def test_afetch_matches_fetch():
    client = WebSearchClient(provider=_FakeProvider())
    sync_out = client.fetch("https://example.com/")
    async_out = await client.afetch("https://example.com/")
    assert async_out == sync_out
    assert "body:https://example.com/" in async_out


@pytest.mark.asyncio
async def test_asearch_structured():
    client = WebSearchClient(provider=_FakeProvider())
    resp = await client.asearch_structured("q")
    assert resp.ok
    assert resp.results[0].title == "Async Title"


@pytest.mark.asyncio
async def test_afetch_structured():
    client = WebSearchClient(provider=_FakeProvider())
    result = await client.afetch_structured("https://example.com/x")
    assert result.ok
    assert result.content == "body:https://example.com/x"
