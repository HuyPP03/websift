from __future__ import annotations

from websift.fetching.detector import is_challenge_or_js_shell
from websift.models import FetchResult


def _html(content: str) -> FetchResult:
    return FetchResult.success("https://example.com", content, content_type="text/html")


def test_detector_matches_compound_challenge_and_specific_js_shell():
    challenge = _html(
        "<html><title>Just a moment...</title>"
        "<script src='/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1'></script></html>"
    )
    js_shell = _html("<html><noscript>Please enable JavaScript to run this app.</noscript></html>")
    assert is_challenge_or_js_shell(challenge)
    assert is_challenge_or_js_shell(js_shell)


def test_detector_can_inspect_raw_html_removed_by_extraction():
    result = _html("Public extracted heading")
    raw_html = (
        "<html><script>window.__cf_chl_opt = {}</script>"
        "<noscript>Enable JavaScript and cookies to continue</noscript></html>"
    )
    assert not is_challenge_or_js_shell(result)
    assert is_challenge_or_js_shell(result, raw_html=raw_html)


def test_detector_rejects_normal_js_heavy_docs_and_loose_phrases():
    docs = _html(
        "<html><title>JavaScript API documentation</title>"
        + "<script src='/assets/docs.js'></script>" * 100
        + "<article>Just a moment in JavaScript measures a point in time. "
        "Enable JavaScript examples in the interactive editor.</article></html>"
    )
    loose_title = _html("<html><title>Just a moment</title><article>Normal article</article></html>")
    platform_only = _html(
        "<html><script src='/cdn-cgi/challenge-platform/example.js'></script>"
        "<article>Cloud platform integration documentation.</article></html>"
    )
    assert not is_challenge_or_js_shell(docs)
    assert not is_challenge_or_js_shell(loose_title)
    assert not is_challenge_or_js_shell(platform_only)


def test_detector_requires_successful_html():
    assert not is_challenge_or_js_shell(
        FetchResult.success("https://example.com", "Just a moment... cf-chl-x", content_type="text/plain")
    )
    assert not is_challenge_or_js_shell(
        FetchResult.failure("https://example.com", "blocked", "blocked", content_type="text/html"),
        raw_html="<title>Just a moment</title><div class='cf-chl-x'></div>",
    )
