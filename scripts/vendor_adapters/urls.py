"""URL canonicalization and SSRF-resistant public-resource checks."""
from __future__ import annotations

import ipaddress
import posixpath
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


class UnsafeUrl(ValueError):
    pass


def _safe_host(hostname: str) -> str:
    host = (hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeUrl("URL is missing a hostname")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise UnsafeUrl("localhost is not a public document host")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        if "." not in host:
            raise UnsafeUrl("single-label hostnames are not public document hosts")
        return host.encode("idna").decode("ascii")
    if not ip.is_global:
        raise UnsafeUrl("non-global IP address rejected")
    return ip.compressed


def _render_authority(host: str, scheme: str, port: int | None) -> str:
    authority = f"[{host}]" if ":" in host else host
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if port and not default_port:
        return f"{authority}:{port}"
    return authority


def canonicalize_url(value: str, base_url: str = "", allowed_hosts: set[str] | None = None) -> str:
    raw = urljoin(base_url, str(value or "").strip())
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrl("malformed URL") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeUrl("only http and https URLs are accepted")
    if parsed.username or parsed.password:
        raise UnsafeUrl("userinfo in URL rejected")
    host = _safe_host(hostname)
    if allowed_hosts:
        normalized = {_safe_host(item) for item in allowed_hosts}
        if host not in normalized and not any(host.endswith("." + suffix) for suffix in normalized):
            raise UnsafeUrl(f"host {host!r} is outside the adapter allowlist")
    netloc = _render_authority(host, scheme, port)
    path = parsed.path or "/"
    path = quote(posixpath.normpath(path), safe="/%:@-._~!$&'()*+,;=")
    if parsed.path.endswith("/") and not path.endswith("/"):
        path += "/"
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
    query.sort(key=lambda pair: (pair[0].lower(), pair[1]))
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def host_allowed(url: str, allowed_hosts: set[str]) -> bool:
    try:
        canonicalize_url(url, allowed_hosts=allowed_hosts)
    except UnsafeUrl:
        return False
    return True
