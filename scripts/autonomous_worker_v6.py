#!/usr/bin/env python3
"""Complete-data worker: require direct product URLs and recover listing-page fragments."""
from __future__ import annotations

import concurrent.futures
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_worker_v5 as v5  # type: ignore

worker = v5.worker
core = v5.core
_original_scan_source = worker.scan_source

_PRODUCT_MARKERS = (
    "/product/",
    "/products/",
    "/product-page/",
    "/l/national/product/",
    "/cbd-hemp-flower/",
    "/hemp-products/",
)
_LISTING_MARKERS = (
    "/product-category/",
    "/product-tag/",
    "/collections/",
    "/category/",
    "/categories/",
)


def is_direct_product_url(value: object) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = urllib.parse.unquote(parsed.path).lower()
    if any(marker in path for marker in _LISTING_MARKERS):
        return False
    return any(marker in path for marker in _PRODUCT_MARKERS)


def normalize_provenance(row: dict) -> dict:
    normalized = dict(row)
    if normalized.get("thca_source") == "variant" and not str(normalized.get("variant") or "").strip():
        normalized["thca_source"] = "product_page"
    return normalized


def recover_listing_row(row: dict) -> list[dict]:
    listing_url = str(row.get("url") or "")
    try:
        payload, content_type, status = core.fetch(listing_url)
    except Exception:
        return []
    if status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return []
    route = ("html", listing_url, "listing_product_recovery")
    candidates = worker.card_candidates(payload, route)
    if not candidates:
        return []

    def resolve(candidate: dict) -> list[dict]:
        product = worker.candidate_to_row(candidate, str(row.get("source_id") or ""), str(row.get("vendor") or ""))
        if not product or not is_direct_product_url(product.get("url")):
            return []
        product_url = v5.canonical_product_url(product.get("url"))
        try:
            product_payload, product_type, product_status = core.fetch(product_url)
        except Exception:
            product_payload, product_type, product_status = "", "", 0
        if product_status == 200 and product_type in {"text/html", "application/xhtml+xml"}:
            expanded = v5.rows_from_embedded_variations(product, product_payload)
            if expanded:
                return [normalize_provenance(item) for item in expanded if is_direct_product_url(item.get("url"))]
        return [normalize_provenance(product)]

    recovered: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
        futures = [executor.submit(resolve, candidate) for candidate in candidates[:80]]
        for future in concurrent.futures.as_completed(futures):
            try:
                recovered.extend(future.result())
            except Exception:
                continue
    return core.dedupe(recovered)


def direct_product_scan_source(source: tuple) -> tuple[list[dict], dict]:
    products, status = _original_scan_source(source)
    if not products:
        return products, status
    direct: list[dict] = []
    listing: list[dict] = []
    for row in products:
        (direct if is_direct_product_url(row.get("url")) else listing).append(normalize_provenance(row))

    recovered: list[dict] = []
    if listing:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(listing))) as executor:
            futures = [executor.submit(recover_listing_row, row) for row in listing]
            for future in concurrent.futures.as_completed(futures):
                try:
                    recovered.extend(future.result())
                except Exception:
                    continue
    final = core.dedupe([*direct, *recovered])
    status = dict(status)
    quality = dict(status.get("quality") or {})
    quality.update(
        direct_product_rows=len(final),
        listing_rows_removed=len(listing),
        listing_rows_recovered=len(recovered),
        potency_products=sum(v5.v4._finite_positive(row.get("thca")) is not None for row in final),
        exact_pricing=sum(row.get("pricing_confidence") in {"exact_variant", "exact_title"} for row in final),
    )
    status.update(products=len(final), quality=quality, worker="autonomous_worker_v6_direct_product_contract")
    return final, status


worker.scan_source = direct_product_scan_source


def self_test() -> int:
    v5.self_test()
    assert is_direct_product_url("https://shop.test/products/blue-dream?variant=1")
    assert is_direct_product_url("https://shop.test/product/blue-dream")
    assert is_direct_product_url("https://shop.test/cbd-hemp-flower/blue-dream")
    assert not is_direct_product_url("https://shop.test/product-category/thca-flower")
    assert not is_direct_product_url("https://shop.test/collections/thca-flower")
    assert not is_direct_product_url("https://shop.test/category/flower")
    assert normalize_provenance({"thca_source": "variant", "variant": ""})["thca_source"] == "product_page"
    assert normalize_provenance({"thca_source": "variant", "variant": "7g"})["thca_source"] == "variant"
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
