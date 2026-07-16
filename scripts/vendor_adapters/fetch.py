"""Bounded, no-cookie public document retrieval with pinned public-address validation."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import http.client
import ipaddress
import socket
import ssl
from typing import Any
from urllib.parse import urlsplit

from .urls import UnsafeUrl, canonicalize_url

DEFAULT_MAX_BYTES = 12_000_000
DEFAULT_TIMEOUT = 15.0
ALLOWED_CONTENT_TYPES = {
    "application/json", "application/ld+json", "application/pdf",
    "text/html", "text/plain", "text/csv", "application/octet-stream",
}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

AddressInfo = tuple[int, int, int, str, tuple[Any, ...]]
Resolver = Callable[..., list[AddressInfo]]
ConnectionFactory = Callable[
    [str, str, int, AddressInfo, float, ssl.SSLContext | None],
    http.client.HTTPConnection,
]


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    error: str = ""
    redirect_chain: tuple[str, ...] = ()


def _address_info_for_literal(hostname: str, port: int) -> AddressInfo | None:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if not address.is_global:
        raise UnsafeUrl("non-global IP address rejected")
    if address.version == 6:
        return (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address.compressed, port, 0, 0))
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address.compressed, port))


def _resolve_public_addresses(
    hostname: str,
    port: int,
    *,
    resolver: Resolver | None = None,
) -> tuple[AddressInfo, ...]:
    literal = _address_info_for_literal(hostname, port)
    if literal is not None:
        return (literal,)

    try:
        answers = (resolver or socket.getaddrinfo)(
            hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except (OSError, socket.gaierror) as exc:
        raise UnsafeUrl(f"hostname resolution failed for {hostname!r}") from exc

    validated: list[AddressInfo] = []
    seen: set[tuple[int, int, int, tuple[Any, ...]]] = set()
    for family, socktype, proto, canonname, sockaddr in answers:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        if socktype not in {0, socket.SOCK_STREAM} or not sockaddr:
            continue
        raw_address = str(sockaddr[0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise UnsafeUrl(f"resolver returned an invalid address for {hostname!r}") from exc
        if (family == socket.AF_INET and address.version != 4) or (
            family == socket.AF_INET6 and address.version != 6
        ):
            raise UnsafeUrl(f"resolver returned an address-family mismatch for {hostname!r}")
        if not address.is_global:
            raise UnsafeUrl(f"hostname {hostname!r} resolved to non-global address {address.compressed}")
        normalized_sockaddr: tuple[Any, ...]
        if address.version == 6:
            flowinfo = int(sockaddr[2]) if len(sockaddr) > 2 else 0
            scope_id = int(sockaddr[3]) if len(sockaddr) > 3 else 0
            normalized_sockaddr = (address.compressed, port, flowinfo, scope_id)
        else:
            normalized_sockaddr = (address.compressed, port)
        normalized = (
            family,
            socktype or socket.SOCK_STREAM,
            proto or socket.IPPROTO_TCP,
            canonname,
            normalized_sockaddr,
        )
        key = (normalized[0], normalized[1], normalized[2], normalized[4])
        if key not in seen:
            seen.add(key)
            validated.append(normalized)

    if not validated:
        raise UnsafeUrl(f"hostname {hostname!r} resolved to no usable public addresses")
    return tuple(validated)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, port: int, address: AddressInfo, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_address = address

    def connect(self) -> None:
        family, socktype, proto, _, sockaddr = self._pinned_address
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(sockaddr)
        except Exception:
            sock.close()
            raise
        self.sock = sock


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        address: AddressInfo,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._pinned_address = address

    def connect(self) -> None:
        family, socktype, proto, _, sockaddr = self._pinned_address
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(sockaddr)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _default_connection_factory(
    scheme: str,
    hostname: str,
    port: int,
    address: AddressInfo,
    timeout: float,
    context: ssl.SSLContext | None,
) -> http.client.HTTPConnection:
    if scheme == "https":
        return _PinnedHTTPSConnection(
            hostname,
            port,
            address,
            timeout,
            context or ssl.create_default_context(),
        )
    return _PinnedHTTPConnection(hostname, port, address, timeout)


def _request_target(url: str) -> str:
    parsed = urlsplit(url)
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    return target


def _host_header(hostname: str, port: int, scheme: str) -> str:
    value = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    return value if port == default_port else f"{value}:{port}"


def _open_pinned(
    url: str,
    *,
    timeout: float,
    user_agent: str,
    resolver: Resolver,
    connection_factory: ConnectionFactory,
    ssl_context: ssl.SSLContext | None,
) -> tuple[http.client.HTTPConnection, Any]:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if scheme == "https" else 80)
    addresses = _resolve_public_addresses(hostname, port, resolver=resolver)
    headers = {
        "Host": _host_header(hostname, port, scheme),
        "User-Agent": user_agent,
        "Accept": "application/json,text/html,application/pdf,text/plain;q=.9,*/*;q=.1",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Connection": "close",
    }

    last_error: Exception | None = None
    for address in addresses:
        connection = connection_factory(scheme, hostname, port, address, timeout, ssl_context)
        try:
            connection.request("GET", _request_target(url), headers=headers)
            return connection, connection.getresponse()
        except Exception as exc:
            last_error = exc
            connection.close()
    if last_error is not None:
        raise last_error
    raise UnsafeUrl(f"hostname {hostname!r} resolved to no usable public addresses")


def fetch_public_document(
    url: str,
    *,
    allowed_hosts: set[str],
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = 4,
    user_agent: str = "DropFinderVendorEvidence/1.0 (+https://github.com/Chicken3veryDay/Drop-finder)",
    _resolver: Resolver | None = None,
    _connection_factory: ConnectionFactory = _default_connection_factory,
    _ssl_context: ssl.SSLContext | None = None,
) -> FetchResult:
    requested = str(url or "")
    try:
        safe = canonicalize_url(requested, allowed_hosts=allowed_hosts)
    except UnsafeUrl as exc:
        return FetchResult(requested, requested, 0, "", b"", f"{type(exc).__name__}: {exc}")

    chain: list[str] = []
    current = safe
    try:
        while True:
            connection, response = _open_pinned(
                current,
                timeout=timeout,
                user_agent=user_agent,
                resolver=_resolver or socket.getaddrinfo,
                connection_factory=_connection_factory,
                ssl_context=_ssl_context,
            )
            try:
                status = int(getattr(response, "status", 200))
                location = response.getheader("Location")
                if status in _REDIRECT_STATUSES and location:
                    if len(chain) >= max_redirects:
                        return FetchResult(
                            safe, current, status, "", b"",
                            "redirect_limit_exceeded", tuple(chain),
                        )
                    current = canonicalize_url(location, base_url=current, allowed_hosts=allowed_hosts)
                    chain.append(current)
                    continue

                if not 200 <= status < 300:
                    return FetchResult(
                        safe, current, status, "", b"",
                        f"http_status_{status}", tuple(chain),
                    )

                content_type = str(response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("image/"):
                    return FetchResult(
                        safe, current, status, content_type, b"",
                        "unsupported_content_type", tuple(chain),
                    )
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    return FetchResult(
                        safe, current, status, content_type, b"",
                        "response_too_large", tuple(chain),
                    )
                return FetchResult(safe, current, status, content_type, body, "", tuple(chain))
            finally:
                response.close()
                connection.close()
    except (
        UnsafeUrl,
        http.client.HTTPException,
        TimeoutError,
        socket.timeout,
        OSError,
        ssl.SSLError,
    ) as exc:
        return FetchResult(
            safe,
            current,
            int(getattr(exc, "code", 0) or 0),
            "",
            b"",
            f"{type(exc).__name__}: {exc}",
            tuple(chain),
        )
