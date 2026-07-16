#!/usr/bin/env python3
"""Bound autonomous storefront requests to public addresses on the original seller host."""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from collections.abc import Callable

Resolver = Callable[..., list[tuple]]


def _canonical_host(value: str) -> tuple[str, int]:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid storefront URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("storefront URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("storefront URL must not contain credentials")
    effective_port = port or (443 if parsed.scheme == "https" else 80)
    if effective_port not in {80, 443}:
        raise ValueError("storefront URL must use a standard HTTP port")
    host = parsed.hostname.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("storefront URL contains an invalid hostname") from exc
    return host, effective_port


def _storefront_identity(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def validate_fetch_target(
    target: str,
    allowed_host: str | None = None,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> tuple[str, int]:
    """Reject cross-host, credentialed, non-standard-port, and non-public requests."""
    host, port = _canonical_host(target)
    if allowed_host is not None and _storefront_identity(host) != _storefront_identity(allowed_host):
        raise ValueError("storefront redirect changed host")

    try:
        literal = ipaddress.ip_address(host)
        addresses = {literal}
    except ValueError:
        try:
            records = resolver(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("storefront hostname resolution failed") from exc
        addresses = set()
        for record in records:
            try:
                addresses.add(ipaddress.ip_address(record[4][0]))
            except (IndexError, ValueError):
                continue
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("storefront URL resolves to a non-public address")
    return host, port


class StorefrontRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_host: str, resolver: Resolver = socket.getaddrinfo) -> None:
        super().__init__()
        self.allowed_host = allowed_host
        self.resolver = resolver

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        validate_fetch_target(newurl, self.allowed_host, resolver=self.resolver)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def install_safe_fetch(core) -> None:  # noqa: ANN001
    """Patch the production scanner's fetch seam once, preserving its response contract."""
    if getattr(core.fetch, "_dropfinder_safe_fetch", False):
        return

    def safe_fetch(target: str):
        allowed_host, _ = validate_fetch_target(target)
        request = urllib.request.Request(
            target,
            headers={
                "User-Agent": core.UA,
                "Accept": "application/json,text/html,application/xml;q=.8,*/*;q=.1",
                "Accept-Encoding": "identity",
            },
        )
        opener = urllib.request.build_opener(StorefrontRedirectHandler(allowed_host))
        with opener.open(request, timeout=core.TIMEOUT) as response:
            raw = response.read(core.LIMIT + 1)
            if len(raw) > core.LIMIT:
                raise ValueError("response too large")
            charset = response.headers.get_content_charset() or "utf-8"
            content_type = str(response.headers.get("Content-Type") or "").split(";")[0].lower()
            return raw.decode(charset, "replace"), content_type, int(getattr(response, "status", 200))

    safe_fetch._dropfinder_safe_fetch = True  # type: ignore[attr-defined]
    core.fetch = safe_fetch


def self_test() -> int:
    public_resolver = lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
    assert validate_fetch_target("https://example.test/products/flower", resolver=public_resolver) == ("example.test", 443)
    assert validate_fetch_target("https://www.example.test/products/flower", "example.test", resolver=public_resolver) == ("www.example.test", 443)

    for target, allowed in (
        ("http://127.0.0.1/internal", None),
        ("http://169.254.169.254/latest/meta-data", None),
        ("https://user:secret@example.test/product", None),
        ("https://example.test:8443/product", None),
        ("https://attacker.test/product", "example.test"),
    ):
        try:
            validate_fetch_target(target, allowed, resolver=public_resolver)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe target accepted: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
