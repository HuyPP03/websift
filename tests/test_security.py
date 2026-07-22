"""SSRF / URL / DNS validation tests (phase 1 hardened behavior)."""

from __future__ import annotations

import socket

import pytest

from web_search.security import is_blocked_ip, is_private_ip, resolve_host, validate_http_url


class TestIsBlockedIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.1",
            "192.168.0.1",
            "169.254.1.1",
            "100.64.0.1",  # CGNAT
            "0.0.0.0",
            "224.0.0.1",  # multicast
            "255.255.255.255",
            "203.0.113.10",  # TEST-NET-3 documentation — not global
            "192.0.2.1",  # TEST-NET-1
            "::1",
            "::",
            "fe80::1",
            "fc00::1",
            "fd12:3456::1",
            "ff02::1",  # IPv6 multicast
            "2001:db8::1",  # documentation
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::ffff:10.0.0.1",
            "::ffff:100.64.0.1",
        ],
    )
    def test_non_global_blocked(self, ip: str):
        assert is_blocked_ip(ip) is True
        assert is_private_ip(ip) is True  # alias

    @pytest.mark.parametrize(
        "ip",
        [
            "8.8.8.8",
            "1.1.1.1",
            "9.9.9.9",
            "2001:4860:4860::8888",
        ],
    )
    def test_global_allowed(self, ip: str):
        assert is_blocked_ip(ip) is False

    def test_unparseable_blocked(self):
        assert is_blocked_ip("not-an-ip") is True
        assert is_blocked_ip("") is True


class TestValidateHttpUrl:
    def test_http_https_ok(self):
        ok, reason, v = validate_http_url("https://Example.COM/path?q=1")
        assert ok is True
        assert reason == ""
        assert v is not None
        assert v.scheme == "https"
        assert v.hostname == "example.com"
        assert v.port == 443

    def test_explicit_port(self):
        ok, _, v = validate_http_url("http://example.com:8080/x")
        assert ok is True
        assert v is not None
        assert v.port == 8080

    def test_blocks_non_http_scheme(self):
        ok, reason, v = validate_http_url("file:///etc/passwd")
        assert ok is False
        assert "http/https" in reason
        assert v is None

    def test_blocks_missing_hostname(self):
        ok, reason, v = validate_http_url("http:///nohost")
        assert ok is False
        assert "hostname" in reason.lower()

    def test_blocks_userinfo(self):
        ok, reason, v = validate_http_url("https://user:pass@example.com/")
        assert ok is False
        assert "credential" in reason.lower()
        assert v is None

    def test_blocks_userinfo_user_only(self):
        ok, reason, _ = validate_http_url("https://user@example.com/")
        assert ok is False
        assert "credential" in reason.lower()

    def test_blocks_malformed_port(self):
        ok, reason, _ = validate_http_url("https://example.com:abc/")
        assert ok is False
        assert "port" in reason.lower()

    def test_blocks_port_out_of_range(self):
        ok, reason, _ = validate_http_url("https://example.com:99999/")
        assert ok is False
        assert "port" in reason.lower()

    def test_blocks_loopback_literal(self):
        ok, reason, _ = validate_http_url("http://127.0.0.1:8080/")
        assert ok is False
        assert "non-global" in reason.lower()

    def test_blocks_private_literal(self):
        ok, reason, _ = validate_http_url("http://192.168.1.1/")
        assert ok is False

    def test_blocks_empty(self):
        ok, reason, _ = validate_http_url("")
        assert ok is False
        assert "empty" in reason.lower()

    def test_idn_hostname_normalized(self):
        # xn-- for IDN; use a simple unicode host if encode works
        ok, reason, v = validate_http_url("https://bücher.example/")
        # May succeed with punycode hostname
        if ok:
            assert v is not None
            assert "xn--" in v.hostname or "bücher" not in v.hostname
        else:
            # environment without idna for this label — still must not crash
            assert reason

    def test_public_ip_literal_allowed(self):
        ok, reason, v = validate_http_url("https://8.8.8.8/path")
        assert ok is True
        assert v is not None
        assert v.hostname == "8.8.8.8"
        assert v.default_port is True

    def test_http_default_port_property(self):
        ok, _, v = validate_http_url("http://example.com/x")
        assert ok and v is not None
        assert v.port == 80
        assert v.default_port is True

    def test_non_default_port_property(self):
        ok, _, v = validate_http_url("https://example.com:8443/")
        assert ok and v is not None
        assert v.default_port is False


class TestResolveHost:
    def test_dns_failure(self, monkeypatch: pytest.MonkeyPatch):
        def _fail(*_a, **_k):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", _fail)
        ok, reason, ip = resolve_host("does-not-resolve.invalid", 443)
        assert ok is False
        assert "DNS resolution failed" in reason
        assert ip == ""

    def test_empty_answers(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [])
        ok, reason, ip = resolve_host("empty.example", 80)
        assert ok is False
        assert "no address" in reason
        assert ip == ""

    def test_private_answer_blocked(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("localhost-like", 80)
        assert ok is False
        assert "non-global" in reason
        assert ip == ""

    def test_public_answers_ok(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("example.test", 443)
        assert ok is True
        assert reason == ""
        assert ip == "8.8.8.8"

    def test_mixed_dns_blocked(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", port)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("mixed.example", 443)
        assert ok is False
        assert "mixed" in reason.lower() or "non-global" in reason.lower()
        assert ip == ""

    def test_all_non_global_blocked(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.0.1", port)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("internal.example", 443)
        assert ok is False
        assert ip == ""

    def test_dedupes_answers(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", port)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("dup.example", 443)
        assert ok is True
        assert ip == "1.1.1.1"

    def test_ipv4_mapped_private_in_dns_blocked(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::ffff:127.0.0.1", port, 0, 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("mapped.example", 443)
        assert ok is False
        assert ip == ""


def test_validate_http_disallow_http_scheme():
    from web_search.security import validate_http_url

    ok, reason, _ = validate_http_url("http://example.com/", allow_http=False)
    assert ok is False
    assert "http" in reason.lower()


def test_validate_allowed_ports():
    from web_search.security import validate_http_url

    ok, _, v = validate_http_url("https://example.com:8443/", allowed_ports=frozenset({80, 443}))
    assert ok is False
    ok2, _, v2 = validate_http_url("https://example.com/", allowed_ports=frozenset({80, 443}))
    assert ok2 is True
    assert v2 is not None and v2.port == 443
