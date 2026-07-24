from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _csv(name: str) -> frozenset[str]:
    return frozenset(item.strip().lower().rstrip(".") for item in os.getenv(name, "").split(",") if item.strip())


def _ports(name: str, default: str) -> frozenset[int]:
    result = frozenset(int(value.strip()) for value in os.getenv(name, default).split(",") if value.strip())
    if not result or any(port < 1 or port > 65535 for port in result):
        raise ValueError(f"{name} contains an invalid port")
    return result


def is_public_bind(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "::1"}:
        return False
    try:
        return not ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return True


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8790
    token: str | None = None
    concurrency: int = 2
    max_request_bytes: int = 32_768
    max_timeout_seconds: float = 45.0
    max_html_bytes: int = 5_000_000
    allow_http: bool = False
    allowed_ports: frozenset[int] = frozenset({443})
    allowed_domains: frozenset[str] = frozenset()
    denied_domains: frozenset[str] = frozenset()
    proxy_connect_timeout: float = 10.0
    proxy_io_timeout: float = 30.0
    proxy_header_timeout: float = 5.0
    proxy_max_header_bytes: int = 32_768
    proxy_max_connections: int = 64

    @classmethod
    def from_env(cls) -> Settings:
        token = os.getenv("BROWSER_TOKEN") or None
        settings = cls(
            host=os.getenv("BROWSER_HOST", "127.0.0.1").strip(),
            port=_int("BROWSER_PORT", 8790, 1, 65535),
            token=token,
            concurrency=_int("BROWSER_CONCURRENCY", 2, 1, 32),
            max_request_bytes=_int("BROWSER_MAX_REQUEST_BYTES", 32_768, 1024, 1_048_576),
            max_timeout_seconds=_float("BROWSER_MAX_TIMEOUT_SECONDS", 45.0, 1.0, 300.0),
            max_html_bytes=_int("BROWSER_MAX_HTML_BYTES", 5_000_000, 1024, 50_000_000),
            allow_http=_bool("BROWSER_ALLOW_HTTP", False),
            allowed_ports=_ports("BROWSER_ALLOWED_PORTS", "443"),
            allowed_domains=_csv("BROWSER_ALLOWED_DOMAINS"),
            denied_domains=_csv("BROWSER_DENIED_DOMAINS"),
            proxy_connect_timeout=_float("BROWSER_PROXY_CONNECT_TIMEOUT", 10.0, 0.1, 60.0),
            proxy_io_timeout=_float("BROWSER_PROXY_IO_TIMEOUT", 30.0, 1.0, 300.0),
            proxy_header_timeout=_float("BROWSER_PROXY_HEADER_TIMEOUT", 5.0, 0.1, 30.0),
            proxy_max_header_bytes=_int("BROWSER_PROXY_MAX_HEADER_BYTES", 32_768, 1024, 262_144),
            proxy_max_connections=_int("BROWSER_PROXY_MAX_CONNECTIONS", 64, 1, 1024),
        )
        if is_public_bind(settings.host) and not settings.token:
            raise ValueError("BROWSER_TOKEN is required when BROWSER_HOST is not loopback")
        if settings.allow_http and 80 not in settings.allowed_ports:
            raise ValueError("BROWSER_ALLOWED_PORTS must include 80 when BROWSER_ALLOW_HTTP is enabled")
        return settings
