from __future__ import annotations

from websift.fetching.backend import FetchBackendOutcome
from websift.fetching.http import HttpFetchBackend
from websift.fetching.orchestrator import FetchOrchestrator
from websift.models import ErrorCategory, FetchResult
from websift.providers.base import FetchContext


class StubBackend:
    fingerprint = "stub-v1"

    def __init__(self, result: FetchResult):
        self.result = result
        self.calls = 0

    def fetch(self, url: str) -> FetchResult:
        self.calls += 1
        return self.result


class OutcomeBackend(StubBackend):
    def __init__(self, result: FetchResult, raw_html: str):
        super().__init__(result)
        self.raw_html = raw_html

    def fetch_outcome(self, url: str) -> FetchBackendOutcome:
        self.calls += 1
        return FetchBackendOutcome(self.result, self.raw_html)


class NativeStage:
    def __init__(self, result: FetchResult | None):
        self.result = result
        self.calls = 0

    def __call__(self, url: str) -> FetchResult | None:
        self.calls += 1
        return self.result


def test_normal_http_success_is_terminal():
    http = StubBackend(FetchResult.success("https://example.com", "ok", content_type="text/html"))
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    result = FetchOrchestrator(http_backend=http, browser_backend=browser).fetch("https://example.com")
    assert result.content == "ok"
    assert http.calls == 1
    assert browser.calls == 0


def test_blocked_http_is_terminal():
    http = StubBackend(FetchResult.failure("https://example.com", "blocked", ErrorCategory.BLOCKED))
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    result = FetchOrchestrator(http_backend=http, browser_backend=browser).fetch("https://example.com")
    assert result.error_category == ErrorCategory.BLOCKED
    assert browser.calls == 0


def test_native_terminal_error_is_terminal():
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    result = FetchOrchestrator(
        http_backend=http,
        native_stage=lambda url: FetchResult.failure(url, "auth", ErrorCategory.AUTH),
    ).fetch("https://example.com")
    assert result.error_category == ErrorCategory.AUTH
    assert http.calls == 0


def test_empty_or_transient_native_falls_to_http():
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    result = FetchOrchestrator(http_backend=http, native_stage=lambda _url: None).fetch("https://example.com")
    assert result.content == "http"
    assert http.calls == 1


def test_browser_mode_skips_native_and_http():
    native = NativeStage(FetchResult.success("https://example.com", "native"))
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    result = FetchOrchestrator(
        http_backend=http,
        browser_backend=browser,
        native_stage=native,
        backend="browser",
    ).fetch("https://example.com")
    assert result.content == "browser"
    assert native.calls == 0
    assert http.calls == 0
    assert browser.calls == 1


def test_http_mode_skips_native_and_browser():
    native = NativeStage(FetchResult.success("https://example.com", "native"))
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    result = FetchOrchestrator(
        http_backend=http,
        browser_backend=browser,
        native_stage=native,
        backend="http",
    ).fetch("https://example.com")
    assert result.content == "http"
    assert native.calls == 0
    assert http.calls == 1
    assert browser.calls == 0


def test_auto_without_browser_returns_http_challenge():
    challenge = FetchResult.success(
        "https://example.com",
        "<html><title>Just a moment...</title><div class='cf-chl-x'></div></html>",
        content_type="text/html",
    )
    result = FetchOrchestrator(http_backend=StubBackend(challenge), backend="auto").fetch("https://example.com")
    assert result is challenge


def test_auto_uses_raw_html_evidence_removed_from_extracted_result():
    extracted = FetchResult.success(
        "https://example.com",
        "Checking access",
        content_type="text/html",
    )
    raw = """<html><title>Checking access</title>
    <script src='/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1'></script>
    <noscript>Please enable JavaScript and cookies to continue</noscript></html>"""
    http = OutcomeBackend(extracted, raw)
    browser = StubBackend(FetchResult.success("https://example.com", "rendered by browser"))

    result = FetchOrchestrator(http_backend=http, browser_backend=browser).fetch("https://example.com")

    assert result.content == "rendered by browser"
    assert http.calls == 1
    assert browser.calls == 1


def test_http_backend_captures_bounded_raw_html_but_returns_extracted_result(monkeypatch):
    raw_html = (
        "<html><body><article>ordinary content</article>"
        "<noscript>Please enable JavaScript to run this app.</noscript></body></html>"
    )
    raw_result = FetchResult.success(
        "https://example.com",
        raw_html,
        content_type="text/html",
        status_code=200,
        bytes_read=len(raw_html),
    )
    monkeypatch.setattr("websift.providers.base.fetch_raw", lambda *_args, **_kwargs: raw_result)
    backend = HttpFetchBackend(FetchContext())

    outcome = backend.fetch_outcome("https://example.com")

    assert "noscript" not in outcome.result.content.lower()
    assert "<noscript>" in outcome.raw_html.lower()
    assert outcome.result.status_code == 200
    assert backend.fetch("https://example.com") == outcome.result


def test_http_error_has_no_raw_body_evidence_in_mvp(monkeypatch):
    failure = FetchResult.failure(
        "https://example.com",
        "Fetch failed: HTTP 403",
        ErrorCategory.HTTP_ERROR,
        content_type="text/html",
        status_code=403,
    )
    monkeypatch.setattr("websift.providers.base.fetch_raw", lambda *_args, **_kwargs: failure)

    outcome = HttpFetchBackend(FetchContext()).fetch_outcome("https://example.com")

    assert outcome.result.status_code == 403
    assert outcome.raw_html == ""


def test_explicit_browser_without_backend_is_config_failure():
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    native = NativeStage(FetchResult.success("https://example.com", "native"))
    result = FetchOrchestrator(
        http_backend=http,
        native_stage=native,
        backend="browser",
    ).fetch("https://example.com")
    assert result.error_category == ErrorCategory.PROVIDER
    assert "requires a configured browser backend" in (result.error_message or "")
    assert native.calls == 0
    assert http.calls == 0


def test_circuit_breaker_skips_browser_escalation():
    """When browser backend has is_available=False, orchestrator returns HTTP result."""
    challenge = FetchResult.success(
        "https://example.com",
        "<html><title>Just a moment...</title><div class='cf-chl-x'></div></html>",
        content_type="text/html",
    )
    raw = """<html><title>Just a moment...</title>
    <script src='/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1'></script></html>"""
    http = OutcomeBackend(challenge, raw)

    # Stub browser with is_available=False (circuit breaker open)
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    browser.is_available = False

    result = FetchOrchestrator(http_backend=http, browser_backend=browser).fetch("https://example.com")

    # Should return HTTP result (challenge page) instead of escalating to browser
    assert result is challenge
    assert browser.calls == 0


def test_circuit_breaker_browser_mode_fails_fast():
    """When backend=browser and circuit breaker open, return NETWORK failure."""
    http = StubBackend(FetchResult.success("https://example.com", "http"))
    browser = StubBackend(FetchResult.success("https://example.com", "browser"))
    browser.is_available = False

    result = FetchOrchestrator(
        http_backend=http,
        browser_backend=browser,
        backend="browser",
    ).fetch("https://example.com")

    assert result.error_category == ErrorCategory.NETWORK
    assert "circuit breaker" in (result.error_message or "").lower()
    assert browser.calls == 0


def test_available_browser_still_escalates(monkeypatch):
    """When is_available=True, browser escalation proceeds normally."""
    from websift.fetching import detector as detector_mod

    # Make detector always return True to trigger escalation
    monkeypatch.setattr(detector_mod, "is_challenge_or_js_shell", lambda *a, **k: True)

    challenge = FetchResult.success(
        "https://example.com",
        "<html><title>Checking...</title></html>",
        content_type="text/html",
    )
    raw = "<html><noscript>Please enable JavaScript to run this app.</noscript></html>"
    http = OutcomeBackend(challenge, raw)
    browser = StubBackend(FetchResult.success("https://example.com", "rendered by browser"))
    browser.is_available = True

    result = FetchOrchestrator(http_backend=http, browser_backend=browser).fetch("https://example.com")

    assert result.content == "rendered by browser"
    assert http.calls == 1
    assert browser.calls == 1
