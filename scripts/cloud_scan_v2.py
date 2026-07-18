#!/usr/bin/env python3
"""Aggregate every successful cloud extraction route before publication."""
from __future__ import annotations

import errno
import socket
import ssl
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
            rows = (
                core.shopify(payload, source_id, vendor, route)
                if route[0] == "shopify"
                else core.woo(payload, source_id, vendor, route)
                if route[0] == "woo"
                else core.html_with_details(payload, source_id, vendor, route)
            )
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


if __name__ == "__main__":
    core.scan = scan_all_routes
    raise SystemExit(core.main())
