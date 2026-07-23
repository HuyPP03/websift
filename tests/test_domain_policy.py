"""Domain allow/deny policy tests."""

from __future__ import annotations

from websift.security import check_domain_policy, hostname_matches_domain, validate_http_url
from websift.settings import AppSettings, FetchSettings


def test_hostname_matches_domain_suffix():
    assert hostname_matches_domain("docs.python.org", "python.org")
    assert hostname_matches_domain("python.org", "python.org")
    assert hostname_matches_domain("a.b.python.org", "*.python.org")
    assert not hostname_matches_domain("notpython.org", "python.org")
    assert not hostname_matches_domain("evil.com", "python.org")


def test_check_domain_policy_allowlist():
    ok, _ = check_domain_policy("docs.python.org", allowed_domains={"python.org"})
    assert ok
    ok, reason = check_domain_policy("evil.example", allowed_domains={"python.org"})
    assert not ok
    assert "ALLOWED" in reason


def test_check_domain_policy_denylist_wins():
    ok, reason = check_domain_policy(
        "ads.python.org",
        allowed_domains={"python.org"},
        denied_domains={"ads.python.org"},
    )
    assert not ok
    assert "DENIED" in reason


def test_validate_http_url_domains():
    ok, _, v = validate_http_url("https://docs.python.org/3/", allowed_domains={"python.org"})
    assert ok and v is not None
    ok2, reason, _ = validate_http_url("https://evil.example/", allowed_domains={"python.org"})
    assert not ok2
    assert "ALLOWED" in reason


def test_settings_loads_domain_env(monkeypatch):
    monkeypatch.setenv("FETCH_ALLOWED_DOMAINS", "example.com, docs.python.org")
    monkeypatch.setenv("FETCH_DENIED_DOMAINS", "ads.example.com")
    s = AppSettings.from_env()
    assert "example.com" in s.fetch.allowed_domains
    assert "docs.python.org" in s.fetch.allowed_domains
    assert "ads.example.com" in s.fetch.denied_domains


def test_fetch_settings_defaults_empty_domain_sets():
    f = FetchSettings()
    assert f.allowed_domains == frozenset()
    assert f.denied_domains == frozenset()
