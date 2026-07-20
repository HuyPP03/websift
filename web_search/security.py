"""SSRF protection: private-IP detection and DNS resolution with pinning."""

import socket


def is_private_ip(ip: str) -> bool:
    """Return True if the IP is loopback, private, or link-local."""
    try:
        packed = socket.inet_pton(socket.AF_INET6 if ":" in ip else socket.AF_INET, ip)
    except OSError:
        return True  # unparseable -> block
    if ":" in ip:
        # IPv6 loopback ::1, link-local fe80::/10, ULA fc00::/7
        if packed == b"\x00" * 15 + b"\x01":
            return True
        if packed[0] in (0xFE, 0xFF) and (packed[1] & 0xC0) == 0x80:
            return True
        if packed[0] in (0xFC, 0xFD):
            return True
    else:
        a, b = packed[0], packed[1]
        if a == 127:
            return True
        if a == 10:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 169 and b == 254:
            return True
    return False


def resolve_host(hostname: str, port: int) -> tuple[bool, str, str]:
    """
    Resolve hostname -> IP with SSRF validation.
    Returns (ok, reason_or_empty, pinned_ip).
    """
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"Blocked: DNS resolution failed for {hostname!r}: {e}", ""
    if not infos:
        return False, f"Blocked: no address found for {hostname!r}.", ""
    ip = infos[0][4][0]
    if is_private_ip(ip):
        return False, f"Blocked: {hostname!r} resolves to a private/loopback address.", ""
    return True, "", ip
