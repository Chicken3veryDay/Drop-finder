#!/usr/bin/env python3
"""Aggregate every successful cloud extraction route before publication."""
from __future__ import annotations
import errno
import socket
import ssl
import time
import urllib.error
import cloud_scan as core

_TRANSIENT_ERRNOS = {
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETUNREACH,
    errno.ETIMEDOUT,
}


def classify_failure(exc: BaseException) -> tuple[str, bool]:
    """Return a stable failure category and bounded-retry decision."""
    if isinstance(exc, urllib.error.HTTPError):
        return "http", False
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, BaseException) and reason is not exc:
            category, retryable = classify_failure(reason)
            if category != "processing_error":
                return category, retryable
        return "invalid_url", False
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout", True
    if isinstance(exc, socket.gaierror):
        return (
            "dns_temporary" if exc.errno == getattr(socket, "EAI_AGAIN", None) else "dns_failure",
            exc.errno == getattr(socket, "EAI_AGAIN", None),
        )
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "tls_certificate", False
    if isinstance(exc, ssl.SSLError):
        return "tls_transport", True
    if isinstance(exc, ConnectionResetError):
        return "connection_reset", True
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused", True
    if isinstance(exc, ConnectionAbortedError):
        return "connection_aborted", True
    if isinstance(exc, OSError) and exc.errno in _TRANSIENT_ERRNOS:
        return "transport_error", True
    return "processing_error", False


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
            result.update(status="http_error", http_status=exc.code, error=f"HTTP {exc.code}", error_category="http")
        except Exception as exc:
            error_category, retryable = classify_failure(exc)
            result.update(
                status="error",
                error=f"{type(exc).__name__}: {core.text(exc)[:220]}",
                error_category=error_category,
                retryable=retryable,
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
