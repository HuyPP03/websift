"""Multi-query search_many tests."""

from __future__ import annotations

import asyncio
import json

from websift.cli import main
from websift.client import WebSearchClient
from websift.models import SearchResult, batch_search_to_dict


class _SeqProvider:
    name = "seq"
    capabilities = type(
        "C",
        (),
        {
            "safe_search": False,
            "region": False,
            "time_range": False,
            "pagination": False,
            "domain_filter": False,
        },
    )()

    def __init__(self):
        self.queries: list[str] = []

    def search(self, request):
        self.queries.append(request.query)
        return [
            SearchResult(
                title=f"T:{request.query}",
                url=f"https://example.com/{request.query}",
                snippet="s",
                rank=1,
                source="seq",
            )
        ]

    def fetch(self, url):
        raise NotImplementedError


def test_search_many_preserves_order():
    p = _SeqProvider()
    client = WebSearchClient(provider=p)
    out = client.search_many(["b", "a", "c"], max_workers=3)
    assert [r.request.query for r in out] == ["b", "a", "c"]
    assert all(r.ok for r in out)
    assert {r.results[0].title for r in out} == {"T:b", "T:a", "T:c"}


def test_search_many_empty():
    client = WebSearchClient(provider=_SeqProvider())
    assert client.search_many([]) == []


def test_search_many_text():
    client = WebSearchClient(provider=_SeqProvider())
    texts = client.search_many_text(["alpha", "beta"], max_workers=2)
    assert len(texts) == 2
    assert all(isinstance(t, str) and t for t in texts)


def test_asearch_many():
    client = WebSearchClient(provider=_SeqProvider())

    async def _run():
        return await client.asearch_many(["x", "y"], max_workers=2)

    out = asyncio.run(_run())
    assert [r.request.query for r in out] == ["x", "y"]
    assert all(r.ok for r in out)


def test_batch_search_to_dict():
    p = _SeqProvider()
    client = WebSearchClient(provider=p)
    items = client.search_many(["x", "y"])
    d = batch_search_to_dict(items)
    assert d["schema_version"] == 2
    assert d["count"] == 2
    assert d["ok"] is True
    assert d["items"][0]["query"] == "x"
    assert d["items"][0]["result_count"] == 1


def test_cli_search_multi_json(capsys, monkeypatch):
    # Force client construction path to use a fake provider via SEARCH_PROVIDER is hard;
    # exercise CLI multi-query envelope by patching WebSearchClient.search_many.
    from websift import cli as cli_mod
    from websift.models import SearchRequest, SearchResponse, SearchResult

    def _fake_many(self, queries, max_workers=None):
        return [
            SearchResponse(
                request=SearchRequest(query=q, max_results=5),
                results=(SearchResult(title=q, url=f"https://e/{q}", snippet="s", rank=1, source="fake"),),
            )
            for q in queries
        ]

    monkeypatch.setattr(cli_mod.WebSearchClient, "search_many", _fake_many)
    try:
        main(["search", "one", "two", "--json"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == 2
    assert data["count"] == 2
    assert data["items"][0]["query"] == "one"
    assert data["items"][1]["query"] == "two"
