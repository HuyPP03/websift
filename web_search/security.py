"""SSRF protection: URL validation, non-global IP policy, DNS resolution with pinning."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse


def is_blocked_ip(ip: str) -> bool:
    """Return True if the IP must not be contacted (non-global / special-use / unparseable).

    Uses :func:`ipaddress.ip_address` and allows only addresses with ``is_global``.
    IPv4-mapped IPv6 addresses are normalized to IPv4 before evaluation.
    Extra flags (multicast/unspecified/…) are checked for defense in depth because
    some CPython versions report certain multicast addresses as ``is_global``.
    """
    try:
        addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip)
    except ValueError:
        return True

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    if (
        addr.is_multicast
        or addr.is_unspecified
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_private
    ):
        return True

    return not addr.is_global


def is_private_ip(ip: str) -> bool:
    """Backward-compatible alias for :func:`is_blocked_ip`."""
    return is_blocked_ip(ip)


@dataclass(frozen=True)
class ValidatedURL:
    """Normalized http(s) URL components safe for outbound fetch."""

    original: str
    scheme: str
    hostname: str
    port: int
    parsed: ParseResult

    @property
    def default_port(self) -> bool:
        return (self.scheme == "https" and self.port == 443) or (self.scheme == "http" and self.port == 80)


def validate_http_url(url: str) -> tuple[bool, str, ValidatedURL | None]:
    """Validate and normalize an absolute http(s) URL for fetch/redirect targets.

    Rules:
    - scheme must be http or https
    - hostname required
    - reject embedded credentials / userinfo
    - port must be in 1..65535 (malformed ports rejected)
    - hostname normalized via IDNA where needed
    """
    if not url or not str(url).strip():
        return False, "Blocked: empty URL.", None

    raw = str(url).strip()
    try:
        parsed = urlparse(raw)
    except Exception as e:  # pragma: no cover - urlparse rarely raises
        return False, f"Blocked: malformed URL: {e}", None

    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked: only http/https allowed (got {parsed.scheme!r}).", None

    # Reject userinfo even when urlparse absorbs it into username/password.
    if parsed.username is not None or parsed.password is not None:
        return False, "Blocked: URL must not contain embedded credentials.", None
    netloc = parsed.netloc or ""
    # userinfo@host — also catch odd forms urlparse might leave in netloc
    if "@" in netloc:
        return False, "Blocked: URL must not contain embedded credentials.", None

    hostname = parsed.hostname
    if not hostname:
        return False, "Blocked: URL missing hostname.", None

    try:
        port = parsed.port
    except ValueError:
        return False, "Blocked: invalid port.", None

    if port is not None and not (1 <= port <= 65535):
        return False, "Blocked: invalid port.", None

    effective_port = port if port is not None else (443 if parsed.scheme == "https" else 80)

    # Normalize IDN hostnames to ASCII (punycode).
    try:
        hostname_ascii = hostname.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return False, f"Blocked: invalid hostname {hostname!r}.", None

    # Reject hostnames that are IP literals if they are non-global (defense in depth;
    # DNS path also checks, but literals never hit DNS).
    try:
        ipaddress.ip_address(hostname_ascii)
    except ValueError:
        pass
    else:
        if is_blocked_ip(hostname_ascii):
            return False, f"Blocked: {hostname_ascii!r} is a non-global address.", None

    return (
        True,
        "",
        ValidatedURL(
            original=raw,
            scheme=parsed.scheme,
            hostname=hostname_ascii,
            port=effective_port,
            parsed=parsed,
        ),
    )


def resolve_host(hostname: str, port: int) -> tuple[bool, str, str]:
    """
    Resolve hostname -> pin one IP after validating *all* DNS answers.

    Returns ``(ok, reason_or_empty, pinned_ip)``.

    If any A/AAAA answer is non-global (or unparseable), the entire hostname is blocked.
    A socket is never opened here; callers must not connect before ``ok`` is True.
    """
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"Blocked: DNS resolution failed for {hostname!r}: {e}", ""

    if not infos:
        return False, f"Blocked: no address found for {hostname!r}.", ""

    unique_ips: list[str] = []
    seen: set[str] = set()
    for info in infos:
        ip = info[4][0]
        if ip not in seen:
            seen.add(ip)
            unique_ips.append(ip)

    blocked = [ip for ip in unique_ips if is_blocked_ip(ip)]
    if blocked:
        if len(unique_ips) == 1:
            return (
                False,
                f"Blocked: {hostname!r} resolves to a non-global address.",
                "",
            )
        return (
            False,
            f"Blocked: {hostname!r} resolves to mixed or non-global address(es).",
            "",
        )

    # All answers global — pin the first unique address.
    return True, "", unique_ips[0]
