"""Compose existing bounded vendor fetch and discovery primitives for publication."""
from __future__ import annotations

from typing import Any, Callable

from .discovery import discover_html_documents, discover_json_documents
from .fetch import FetchResult, fetch_public_document
from .models import DocumentCandidate
from .publication_common import product_id, product_url, timestamp, vendor_id

FetchCallable = Callable[..., FetchResult]


def _check(
    vendor: str,
    kind: str,
    url: str,
    result: FetchResult | None = None,
    *,
    candidate_count: int = 0,
    error: str = "",
) -> dict[str, Any]:
    return {
        "vendor_id": vendor,
        "kind": kind,
        "url": url,
        "final_url": result.final_url if result else "",
        "status": result.status if result else 0,
        "content_type": result.content_type if result else "",
        "bytes": len(result.body) if result else 0,
        "candidate_count": candidate_count,
        "ok": bool(result and 200 <= result.status < 300 and not result.error and not error),
        "error": error or (result.error if result else ""),
    }


def _discover(
    result: FetchResult,
    *,
    vendor: str,
    hosts: set[str],
    observed_at: str,
    target_product_id: str = "",
) -> list[DocumentCandidate]:
    source_url = result.final_url or result.requested_url
    payload = result.body.decode("utf-8", "replace")
    if result.content_type in {"application/json", "application/ld+json"}:
        return discover_json_documents(
            payload,
            vendor_id=vendor,
            source_url=source_url,
            allowed_hosts=hosts,
            observed_at=observed_at,
        )
    if result.content_type in {"text/html", "text/plain", "text/csv", ""}:
        return discover_html_documents(
            payload,
            vendor_id=vendor,
            page_url=source_url,
            allowed_hosts=hosts,
            observed_at=observed_at,
            product_id=target_product_id,
        )
    return []


def _probe(
    *,
    vendor: str,
    url: str,
    kind: str,
    hosts: set[str],
    observed_at: str,
    timeout: float,
    max_bytes: int,
    fetcher: FetchCallable,
    target_product_id: str = "",
) -> tuple[list[DocumentCandidate], dict[str, Any]]:
    try:
        result = fetcher(url, allowed_hosts=hosts, timeout=timeout, max_bytes=max_bytes)
    except Exception as exc:
        return [], _check(vendor, kind, url, error=f"{type(exc).__name__}: {exc}")
    if not (200 <= result.status < 300) or result.error:
        return [], _check(vendor, kind, url, result)
    try:
        rows = _discover(
            result,
            vendor=vendor,
            hosts=hosts,
            observed_at=observed_at,
            target_product_id=target_product_id,
        )
    except Exception as exc:
        return [], _check(vendor, kind, url, result, error=f"{type(exc).__name__}: {exc}")
    return rows, _check(vendor, kind, url, result, candidate_count=len(rows))


def _dedupe(rows: list[DocumentCandidate]) -> list[DocumentCandidate]:
    selected: dict[tuple[str, str, str, str], DocumentCandidate] = {}
    for row in rows:
        key = (
            row.document_id,
            row.product_id,
            row.variant_id or row.variant_label,
            "" if row.weight_grams is None else f"{row.weight_grams:.4f}",
        )
        selected.setdefault(key, row)
    return sorted(
        selected.values(),
        key=lambda row: (
            row.vendor_id,
            row.document_kind,
            row.url,
            row.product_id,
            row.variant_id,
            row.variant_label,
        ),
    )


def collect_candidates(
    products: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
    offline: bool = False,
    timeout: float = 10.0,
    max_index_bytes: int = 2_000_000,
    max_product_page_bytes: int = 1_000_000,
    max_product_pages_per_vendor: int = 12,
    fetcher: FetchCallable = fetch_public_document,
) -> tuple[list[DocumentCandidate], list[dict[str, Any]]]:
    stamp = timestamp(observed_at)
    by_vendor: dict[str, list[dict[str, Any]]] = {}
    for product in products:
        if vendor_id(product):
            by_vendor.setdefault(vendor_id(product), []).append(product)

    candidates: list[DocumentCandidate] = []
    checks: list[dict[str, Any]] = []
    for profile in profiles:
        vendor = str(profile.get("vendor_id") or "")
        vendor_products = sorted(
            by_vendor.get(vendor, []),
            key=lambda row: (product_url(row), product_id(row)),
        )
        if not vendor_products:
            continue
        hosts = {str(item).lower() for item in profile.get("allowed_document_hosts") or []}
        index_urls = sorted(str(item) for item in profile.get("lab_index_urls") or [])
        if offline:
            checks.extend(_check(vendor, "lab_index", url, error="offline_not_run") for url in index_urls)
            continue

        for url in index_urls:
            found, check = _probe(
                vendor=vendor,
                url=url,
                kind="lab_index",
                hosts=hosts,
                observed_at=stamp,
                timeout=timeout,
                max_bytes=max_index_bytes,
                fetcher=fetcher,
            )
            candidates.extend(found)
            checks.append(check)

        adapter = profile.get("adapter") if isinstance(profile.get("adapter"), dict) else {}
        labs = profile.get("labs") if isinstance(profile.get("labs"), dict) else {}
        public_labs = any(
            labs.get(field) in {"public", "partial"}
            for field in ("coa_availability", "terpene_availability")
        )
        if adapter.get("product_page_discovery") is not True or not public_labs:
            continue
        seen: set[str] = set()
        for product in vendor_products:
            url = product_url(product)
            target_id = product_id(product)
            if not url or not target_id or url in seen:
                continue
            seen.add(url)
            if len(seen) > max(0, max_product_pages_per_vendor):
                break
            found, check = _probe(
                vendor=vendor,
                url=url,
                kind="product_page",
                hosts=hosts,
                observed_at=stamp,
                timeout=timeout,
                max_bytes=max_product_page_bytes,
                fetcher=fetcher,
                target_product_id=target_id,
            )
            candidates.extend(found)
            checks.append(check)

    checks.sort(key=lambda row: (row["vendor_id"], row["kind"], row["url"]))
    return _dedupe(candidates), checks
