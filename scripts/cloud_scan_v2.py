#!/usr/bin/env python3
"""Aggregate every successful cloud extraction route before publication."""
from __future__ import annotations

import errno
import socket
import ssl
import sys
import time
import urllib.error

import cloud_scan as core


_TRANSIENT_ERRNOS = frozenset(
    getattr(errno, name)
    for name in (
        "ECONNABORTED",
        "ECONNREFUSED",
        "ECONNRESET",
        "EHOSTUNREACH",
        "ENETDOWN",
        "ENETRESET",
        "ENETUNREACH",
        "ETIMEDOUT",
    )
    if hasattr(errno, name)
)


def classify_route_failure(exc: BaseException) -> dict:
    """Preserve retry semantics without parsing user-facing error strings."""
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        category, retryable = "tls_certificate_error", False
    elif isinstance(reason, TimeoutError):
        category, retryable = "transport_timeout", True
    elif isinstance(reason, socket.gaierror):
        retryable = reason.errno == getattr(socket, "EAI_AGAIN", None)
        category = "temporary_dns_failure" if retryable else "dns_failure"
    elif isinstance(reason, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
        category, retryable = "tls_transport_failure", True
    elif isinstance(reason, ConnectionError):
        category, retryable = "connection_failure", True
    elif isinstance(reason, OSError) and reason.errno in _TRANSIENT_ERRNOS:
        category, retryable = "transport_os_error", True
    elif isinstance(exc, urllib.error.URLError):
        category, retryable = "url_error", False
    else:
        category, retryable = "processing_error", False
    return {"error_category": category, "retryable": retryable}


def _parse_route(payload: str, source_id: str, vendor: str, route: tuple) -> tuple[list[dict], dict]:
    """Normalize parser-specific return contracts into rows plus diagnostics."""
    if route[0] == "shopify":
        parsed = core.shopify(payload, source_id, vendor, route)
        diagnostics = {}
    elif route[0] == "woo":
        parsed = core.woo(payload, source_id, vendor, route)
        if (
            isinstance(parsed, tuple)
            and len(parsed) == 2
            and isinstance(parsed[1], dict)
        ):
            parsed, diagnostics = parsed
        else:
            diagnostics = {}
    else:
        diagnostics = {}
        parsed = core.html_with_details(
            payload, source_id, vendor, route, diagnostics
        )

    if not isinstance(parsed, list) or any(not isinstance(row, dict) for row in parsed):
        raise TypeError(f"{route[0]} parser returned an invalid row collection")
    return parsed, diagnostics


def scan_all_routes(source):
    source_id, vendor, routes = source
    started = time.monotonic()
    attempts = []
    all_rows = []
    active_route = ""
    active_count = -1

    for index, route in enumerate(routes, 1):
        result = {
            "route_id": f"{source_id}-{index}",
            "url": route[1],
            "source_type": route[0],
        }
        route_started = time.monotonic()
        try:
            payload, content_type, status = core.fetch(route[1])
            result.update(http_status=status, content_type=content_type)
            if status != 200:
                raise ValueError(f"unexpected HTTP status {status}")
            rows, diagnostics = _parse_route(payload, source_id, vendor, route)
            result.update(diagnostics)
            result.update(
                status="healthy" if rows else "empty",
                products=len(rows),
                duration_seconds=round(time.monotonic() - route_started, 3),
            )
            attempts.append(result)
            all_rows.extend(rows)
            if len(rows) > active_count:
                active_count = len(rows)
                active_route = route[1] if rows else active_route
        except urllib.error.HTTPError as exc:
            result.update(
                status="http_error",
                http_status=exc.code,
                error_category="http_status",
                error=f"HTTP {exc.code}",
            )
        except Exception as exc:
            failure = (
                {"error_category": "http_status"}
                if result.get("http_status") is not None
                else classify_route_failure(exc)
            )
            result.update(
                status="error",
                error=f"{type(exc).__name__}: {core.text(exc)[:220]}",
                **failure,
            )
        if not attempts or attempts[-1] is not result:
            result["duration_seconds"] = round(time.monotonic() - route_started, 3)
            attempts.append(result)

    rows = core.dedupe(all_rows)
    return rows, {
        "source_id": source_id,
        "name": vendor,
        "enabled": True,
        "status": "healthy" if rows else "degraded",
        "products": len(rows),
        "routes_attempted": len(attempts),
        "active_route": active_route,
        "route_results": attempts,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def self_test() -> int:
    """Exercise the aggregate contract without network access."""
    original_fetch = core.fetch
    original_woo = core.woo
    route = (
        "woo",
        "https://example.test/wp-json/wc/store/v1/products?per_page=100",
        "storewide",
    )
    fixture_row = {
        "source_id": "fixture",
        "vendor": "Fixture",
        "name": "Fixture Product",
        "url": "https://example.test/product/fixture",
        "variant": "",
        "price": 10.0,
    }

    core.fetch = lambda _target: ("{}", "application/json", 200)
    core.woo = lambda *_args: (
        [fixture_row],
        {
            "variable_parents": 1,
            "variation_requests": 2,
            "variation_retries": 0,
            "variation_failures": 0,
            "variation_failure_reasons": {},
            "variation_rejections": 0,
            "variation_rejection_reasons": {},
        },
    )
    try:
        rows, status = scan_all_routes(("fixture", "Fixture", [route]))
    finally:
        core.fetch = original_fetch
        core.woo = original_woo

    assert rows == [fixture_row]
    assert status["products"] == 1
    result = status["route_results"][0]
    assert result["status"] == "healthy"
    assert result["variable_parents"] == 1
    assert result["variation_requests"] == 2
    print("aggregate parser-contract self-test passed")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        core.selftest()
        raise SystemExit(self_test())
    core.scan = scan_all_routes
    raise SystemExit(core.main())
