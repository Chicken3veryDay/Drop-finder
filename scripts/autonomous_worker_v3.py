#!/usr/bin/env python3
"""Browser-compatible transport layer for autonomous DropFinder workers."""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_worker_v2 as reliability  # type: ignore

worker = reliability.worker

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
TRANSIENT = {202, 408, 425, 429, 500, 502, 503, 504}
DELAYS = (0.0, 2.0, 5.0)
_original_fetch = worker.core.fetch

worker.FALLBACK_HTML_ROUTES.setdefault(
    "arete",
    ["https://arete.shop/l/national/products/category/thca-flower"],
)
if "/l/national/product/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/l/national/product/")


def _browser_request(target: str) -> tuple[str, str, int]:
    request = urllib.request.Request(
        target,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    with urllib.request.urlopen(request, timeout=worker.core.TIMEOUT) as response:
        raw = response.read(worker.core.LIMIT + 1)
        if len(raw) > worker.core.LIMIT:
            raise ValueError("response too large")
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace"), content_type, int(getattr(response, "status", 200))


def browser_compatible_fetch(target: str) -> tuple[str, str, int]:
    """Use the lightweight client first, then a browser-shaped request when blocked."""
    last_error: Exception | None = None
    for attempt, delay in enumerate(DELAYS, start=1):
        if delay:
            time.sleep(delay)
        methods = (_original_fetch, _browser_request) if attempt == 1 else (_browser_request,)
        for method in methods:
            try:
                payload, content_type, status = method(target)
                if status in TRANSIENT:
                    last_error = RuntimeError(f"transient HTTP {status}")
                    continue
                if not 200 <= status < 300:
                    last_error = RuntimeError(f"HTTP {status}")
                    continue
                return payload, content_type, status
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in ({403, 406} | TRANSIENT):
                    raise
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
                last_error = exc
        if last_error and isinstance(last_error, urllib.error.HTTPError) and last_error.code not in TRANSIENT:
            break
    if last_error:
        raise last_error
    raise RuntimeError("fetch failed without an error")


worker.core.fetch = browser_compatible_fetch


def self_test() -> int:
    reliability.self_test()
    assert "arete" in worker.FALLBACK_HTML_ROUTES
    assert "/l/national/product/" in worker.PRODUCT_PATHS
    assert 202 in TRANSIENT and 429 in TRANSIENT and 503 in TRANSIENT
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
