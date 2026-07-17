"""Bounded, no-cookie public document retrieval with redirect validation."""
from __future__ import annotations

from dataclasses import dataclass
import socket
import urllib.error
import urllib.request

from .urls import UnsafeUrl, canonicalize_url

DEFAULT_MAX_BYTES = 12_000_000
DEFAULT_TIMEOUT = 15.0
ALLOWED_CONTENT_TYPES = {
    "application/json", "application/ld+json", "application/pdf",
    "text/html", "text/plain", "text/csv", "application/octet-stream",
}


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    error: str = ""
    redirect_chain: tuple[str, ...] = ()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str], chain: list[str], max_redirects: int) -> None:
        self.allowed_hosts = allowed_hosts
        self.chain = chain
        self.max_redirects = max_redirects
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if len(self.chain) >= self.max_redirects:
            raise urllib.error.HTTPError(req.full_url, code, "redirect limit exceeded", headers, fp)
        safe = canonicalize_url(newurl, base_url=req.full_url, allowed_hosts=self.allowed_hosts)
        self.chain.append(safe)
        return super().redirect_request(req, fp, code, msg, headers, safe)


def fetch_public_document(
    url: str,
    *,
    allowed_hosts: set[str],
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = 4,
    user_agent: str = "DropFinderVendorEvidence/1.0 (+https://github.com/Chicken3veryDay/Drop-finder)",
) -> FetchResult:
    safe = ""
    chain: list[str] = []
    try:
        safe = canonicalize_url(url, allowed_hosts=allowed_hosts)
        handler = _SafeRedirectHandler(allowed_hosts, chain, max_redirects)
        opener = urllib.request.build_opener(handler)
        request = urllib.request.Request(
            safe,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json,text/html,application/pdf,text/plain;q=.9,*/*;q=.1",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-cache",
            },
            method="GET",
        )
        with opener.open(request, timeout=timeout) as response:
            final_url = canonicalize_url(response.geturl(), allowed_hosts=allowed_hosts)
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("image/"):
                return FetchResult(safe, final_url, status, content_type, b"", "unsupported_content_type", tuple(chain))
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return FetchResult(safe, final_url, status, content_type, b"", "response_too_large", tuple(chain))
            return FetchResult(safe, final_url, status, content_type, body, "", tuple(chain))
    except (UnsafeUrl, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, OSError) as exc:
        final_url = chain[-1] if chain else safe
        return FetchResult(safe, final_url, int(getattr(exc, "code", 0) or 0), "", b"", f"{type(exc).__name__}: {exc}", tuple(chain))
