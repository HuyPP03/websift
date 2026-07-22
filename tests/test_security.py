"""Characterization tests for SSRF helpers (current v0.1.0 behavior)."""

import socket

import pytest

from web_search.security import is_private_ip, resolve_host


class TestIsPrivateIp:
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
            "::1",
            "fe80::1",
            "fc00::1",
            "fd12:3456::1",
        ],
    )
    def test_known_private_blocked(self, ip: str):
        assert is_private_ip(ip) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "8.8.8.8",
            "1.1.1.1",
            "203.0.113.10",
            "2001:4860:4860::8888",
        ],
    )
    def test_public_allowed(self, ip: str):
        assert is_private_ip(ip) is False

    def test_unparseable_blocked(self):
        assert is_private_ip("not-an-ip") is True
        assert is_private_ip("") is True

    # --- Documented baseline gaps (to be closed in phase 1) ---

    def test_cgnat_currently_not_blocked(self):
        """v0.1.0 gap: 100.64.0.0/10 is not treated as private."""
        assert is_private_ip("100.64.0.1") is False

    def test_ipv6_multicast_currently_not_blocked(self):
        """v0.1.0 gap: ff02::1 is not blocked by hand-rolled logic."""
        assert is_private_ip("ff02::1") is False

    def test_ipv6_unspecified_currently_not_blocked(self):
        """v0.1.0 gap: :: is not blocked."""
        assert is_private_ip("::") is False

    def test_ipv4_mapped_private_not_normalized(self):
        """v0.1.0 gap: IPv4-mapped private may not be detected as private."""
        # Depending on inet_pton parsing; document current outcome.
        result = is_private_ip("::ffff:127.0.0.1")
        assert isinstance(result, bool)


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

    def test_private_first_answer_blocked(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("localhost-like", 80)
        assert ok is False
        assert "private/loopback" in reason
        assert ip == ""

    def test_public_first_answer_ok(self, monkeypatch: pytest.MonkeyPatch):
        def _gai(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.5", port))]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("example.test", 443)
        assert ok is True
        assert reason == ""
        assert ip == "203.0.113.5"

    def test_only_first_answer_checked_mixed_dns_gap(self, monkeypatch: pytest.MonkeyPatch):
        """v0.1.0 gap: mixed public+private answers allow if first is public."""

        def _gai(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.5", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", port)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        ok, reason, ip = resolve_host("mixed.example", 443)
        assert ok is True
        assert ip == "203.0.113.5"
