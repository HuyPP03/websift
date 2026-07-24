from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import Settings


class BlockedTarget(ValueError):
    pass


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not domain or "/" in domain or "@" in domain:
        raise BlockedTarget("invalid domain policy")
    try:
        return ipaddress.ip_address(domain).compressed
    except ValueError:
        if ":" in domain:
            raise BlockedTarget("invalid domain policy") from None
    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise BlockedTarget("invalid domain policy") from exc


def domain_matches(host: str, rule: str) -> bool:
    return host == rule or host.endswith(f".{rule}")


@dataclass(frozen=True)
class EffectivePolicy:
    allow_http: bool
    allowed_ports: frozenset[int]
    allowed_domains: frozenset[str]
    denied_domains: frozenset[str]

    def validate_url(self, url: str, *, allow_local_scheme: bool = True) -> None:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme in {"data", "blob"} and allow_local_scheme:
            return
        if scheme not in {"http", "https"}:
            raise BlockedTarget("URL scheme is blocked")
        if parsed.username is not None or parsed.password is not None:
            raise BlockedTarget("URL userinfo is blocked")
        if not parsed.hostname:
            raise BlockedTarget("URL hostname is required")
        if scheme == "http" and not self.allow_http:
            raise BlockedTarget("HTTP targets are blocked")
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise BlockedTarget("URL port is invalid") from exc
        if port not in self.allowed_ports:
            raise BlockedTarget("Target port is blocked")
        host = normalize_domain(parsed.hostname)
        if any(domain_matches(host, rule) for rule in self.denied_domains):
            raise BlockedTarget("Target domain is blocked")
        if self.allowed_domains and not any(domain_matches(host, rule) for rule in self.allowed_domains):
            raise BlockedTarget("Target domain is not allowed")


def merge_policy(
    settings: Settings,
    *,
    allow_http: bool,
    allowed_ports: set[int],
    allowed_domains: set[str],
    denied_domains: set[str],
) -> EffectivePolicy:
    requested_ports = frozenset(allowed_ports)
    if not requested_ports or not requested_ports.issubset(settings.allowed_ports):
        raise BlockedTarget("Requested ports exceed daemon policy")
    if allow_http and not settings.allow_http:
        raise BlockedTarget("Requested HTTP access exceeds daemon policy")

    daemon_allowed = frozenset(normalize_domain(item) for item in settings.allowed_domains)
    requested_allowed = frozenset(normalize_domain(item) for item in allowed_domains)
    if daemon_allowed:
        if not requested_allowed:
            effective_allowed = daemon_allowed
        elif not all(any(domain_matches(rule, daemon) for daemon in daemon_allowed) for rule in requested_allowed):
            raise BlockedTarget("Requested domains exceed daemon policy")
        else:
            effective_allowed = requested_allowed
    else:
        effective_allowed = requested_allowed

    effective_denied = frozenset(normalize_domain(item) for item in settings.denied_domains | denied_domains)
    return EffectivePolicy(
        allow_http=settings.allow_http and allow_http,
        allowed_ports=requested_ports,
        allowed_domains=effective_allowed,
        denied_domains=effective_denied,
    )
