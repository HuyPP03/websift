from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import Settings
from .policy import BlockedTarget, EffectivePolicy, normalize_domain

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def parse_connect_target(target: str) -> tuple[str, int]:
    if not target or "@" in target or "/" in target:
        raise BlockedTarget("invalid CONNECT target")
    if target.startswith("["):
        end = target.find("]")
        if end < 0 or end + 1 >= len(target) or target[end + 1] != ":":
            raise BlockedTarget("invalid CONNECT target")
        host, port_text = target[1:end], target[end + 2 :]
    else:
        if target.count(":") != 1:
            raise BlockedTarget("invalid CONNECT target")
        host, port_text = target.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError as exc:
        raise BlockedTarget("invalid CONNECT port") from exc
    if not host or not 1 <= port <= 65535:
        raise BlockedTarget("invalid CONNECT target")
    return normalize_domain(host), port


def filter_headers(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    connection_tokens: set[str] = set()
    for name, value in headers:
        if name.lower() == "connection":
            connection_tokens.update(token.strip().lower() for token in value.split(","))
    blocked = _HOP_BY_HOP | connection_tokens
    return [(name, value) for name, value in headers if name.lower() not in blocked]


def rewrite_http_request(
    method: str, target: str, version: str, headers: list[tuple[str, str]]
) -> tuple[bytes, str, int]:
    parsed = urlsplit(target)
    if parsed.scheme.lower() != "http" or not parsed.hostname or parsed.username is not None:
        raise BlockedTarget("proxy requires an absolute HTTP target")
    try:
        port = parsed.port or 80
    except ValueError as exc:
        raise BlockedTarget("invalid HTTP target port") from exc
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    clean_headers = filter_headers(headers)
    if not any(name.lower() == "host" for name, _ in clean_headers):
        authority = parsed.hostname if port == 80 else f"{parsed.hostname}:{port}"
        clean_headers.append(("Host", authority))
    lines = [f"{method} {path} {version}", *(f"{name}: {value}" for name, value in clean_headers), "", ""]
    return "\r\n".join(lines).encode("latin-1"), normalize_domain(parsed.hostname), port


def _safe_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


async def resolve_global(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    answers = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or not all(_safe_ip(address) for address in addresses):
        raise BlockedTarget("target DNS resolves to a non-global address")
    return addresses


@dataclass
class EgressProxy:
    settings: Settings

    def __post_init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._slots = asyncio.Semaphore(self.settings.proxy_max_connections)
        self.host = "127.0.0.1"
        self.port = 0
        self.policy = EffectivePolicy(
            allow_http=self.settings.allow_http,
            allowed_ports=self.settings.allowed_ports,
            allowed_domains=frozenset(normalize_domain(item) for item in self.settings.allowed_domains),
            denied_domains=frozenset(normalize_domain(item) for item in self.settings.denied_domains),
        )

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, self.host, 0, limit=self.settings.proxy_max_header_bytes + 1
        )
        socket_name = self._server.sockets[0].getsockname()
        self.port = int(socket_name[1])

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def url(self) -> str:
        if not self.port:
            raise RuntimeError("proxy is not started")
        return f"http://{self.host}:{self.port}"

    async def _read_headers(self, reader: asyncio.StreamReader) -> bytes:
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.settings.proxy_header_timeout)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError) as exc:
            raise BlockedTarget("invalid or oversized proxy headers") from exc
        if len(data) > self.settings.proxy_max_header_bytes:
            raise BlockedTarget("proxy headers are too large")
        return data

    async def _connect(self, host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        addresses = await resolve_global(host, port)
        last_error: OSError | None = None
        for address in addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(address, port, family=family, server_hostname=None),
                    self.settings.proxy_connect_timeout,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                last_error = exc if isinstance(exc, OSError) else OSError("connect timeout")
        raise OSError("target connection failed") from last_error

    def _validate_host_port(self, host: str, port: int, scheme: str) -> None:
        authority_host = f"[{host}]" if ":" in host else host
        self.policy.validate_url(f"{scheme}://{authority_host}:{port}/", allow_local_scheme=False)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream: asyncio.StreamWriter | None = None
        try:
            async with self._slots:
                raw = await self._read_headers(reader)
                text = raw.decode("latin-1")
                lines = text[:-4].split("\r\n")
                parts = lines[0].split(" ")
                if len(parts) != 3 or parts[2] not in {"HTTP/1.0", "HTTP/1.1"}:
                    raise BlockedTarget("invalid proxy request line")
                method, target, version = parts
                headers = []
                for line in lines[1:]:
                    if not line or line[0].isspace() or ":" not in line:
                        raise BlockedTarget("invalid proxy header")
                    name, value = line.split(":", 1)
                    headers.append((name.strip(), value.strip()))
                if method.upper() == "CONNECT":
                    host, port = parse_connect_target(target)
                    self._validate_host_port(host, port, "https")
                    upstream_reader, upstream = await self._connect(host, port)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                else:
                    request, host, port = rewrite_http_request(method, target, version, headers)
                    self._validate_host_port(host, port, "http")
                    upstream_reader, upstream = await self._connect(host, port)
                    upstream.write(request)
                    await upstream.drain()
                await self._tunnel(reader, writer, upstream_reader, upstream)
        except BlockedTarget:
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except (OSError, asyncio.TimeoutError, UnicodeError):
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        finally:
            if upstream:
                upstream.close()
                await upstream.wait_closed()
            writer.close()
            await writer.wait_closed()

    async def _tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
            while True:
                data = await asyncio.wait_for(source.read(65_536), self.settings.proxy_io_timeout)
                if not data:
                    break
                destination.write(data)
                await destination.drain()

        tasks = [
            asyncio.create_task(copy(client_reader, upstream_writer)),
            asyncio.create_task(copy(upstream_reader, client_writer)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
