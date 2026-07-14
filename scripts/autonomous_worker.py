#!/usr/bin/env python3
"""Run real storefront retrieval workers on deterministic GitHub Actions shards."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloud_scan as core  # type: ignore
import cloud_scan_v2 as aggregate  # type: ignore

PRICE = re.compile(r"\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)")
PRODUCT_PATHS = ("/product/", "/products/", "/l/national/products/", "/shop/")
CONTEXT = {
    "black_tie_cbd": "THCA Flower",
    "preston_herb_co": "High THCA Flower",
    "holy_city_farms": "THCA Flower",
    "wnc_cbd": "High THCA Flower",
    "secret_nature": "THCA Flower",
    "five_leaf_wellness": "THCA Flower",
}
EXTRA_HTML_ROUTES = {
    "secret_nature": [
        "https://secretnature.com/collections/thca-flower",
        "https://secretnaturecbd.com/collections/thca-flower",
    ],
    "five_leaf_wellness": [
        "https://fiveleafwellness.com/product-category/thca-flower/",
        "https://fiveleafwellness.com/product-category/flower/",
    ],
}


def gate(products: list[dict]) -> tuple[bool, list[str], dict]:
    reasons: list[str] = []
    count = len(products)
    valid_urls = sum(bool(str(row.get("url") or "").strip()) for row in products)
    priced = sum(core.num(row.get("price")) is not None for row in products)
    if count == 0:
        reasons.append("no_qualifying_products")
    if count and valid_urls / count < 0.90:
        reasons.append("insufficient_product_urls")
    if count and priced == 0:
        reasons.append("no_priced_products")
    return not reasons, reasons, {
        "products": count,
        "url_coverage": round(valid_urls / count, 4) if count else 0,
        "priced_products": priced,
    }


def card_rows(payload: str, source_id: str, vendor: str, route: tuple) -> list[dict]:
    """Conservative fallback for storefront cards omitted from JSON-LD/API output."""
    context = CONTEXT.get(source_id)
    if not context:
        return []
    base_host = urllib.parse.urlsplit(route[1]).netloc.lower()
    rows: list[dict] = []
    for match in core.ANCHOR.finditer(payload):
        target = core.url(match.group(1), route[1])
        parsed = urllib.parse.urlsplit(target)
        if not target or parsed.netloc.lower() != base_host:
            continue
        path = parsed.path.lower()
        if not any(marker in path for marker in PRODUCT_PATHS):
            continue
        label = core.text(match.group(2))
        if len(label) < 4 or label.lower() in {"options", "view product", "learn more", "shop now"}:
            continue
        combined = f"{label} {context}"
        if core.HARD_EXCLUDE.search(combined):
            continue
        # Product cards generally place price/stock immediately after the title link.
        nearby = core.text(payload[match.start() : min(len(payload), match.end() + 2200)])
        prices = [core.num(value) for value in PRICE.findall(nearby)]
        price = next((value for value in prices if value is not None), None)
        stock = "out_of_stock" if "out of stock" in nearby.lower() else "in_stock" if any(token in nearby.lower() for token in ("add to cart", "choose an option", "in stock")) else ""
        row = core.record(source_id, vendor, route, label, target, context, price, stock)
        if row:
            rows.append(row)
    return core.dedupe(rows)


def fallback_scan(source: tuple) -> tuple[list[dict], list[dict]]:
    source_id, vendor, routes = source
    candidates = list(routes)
    existing = {route[1] for route in candidates}
    for target in EXTRA_HTML_ROUTES.get(source_id, []):
        if target not in existing:
            candidates.append(("html", target, "thca_flower"))
    rows: list[dict] = []
    attempts: list[dict] = []
    for index, route in enumerate(candidates, 1):
        if route[0] != "html":
            continue
        started = time.monotonic()
        result = {
            "route_id": f"{source_id}-fallback-{index}",
            "url": route[1],
            "source_type": "html_card_fallback",
        }
        try:
            payload, content_type, http_status = core.fetch(route[1])
            extracted = card_rows(payload, source_id, vendor, route)
            result.update(
                http_status=http_status,
                content_type=content_type,
                status="healthy" if extracted else "empty",
                products=len(extracted),
            )
            rows.extend(extracted)
        except Exception as exc:
            result.update(status="error", error=f"{type(exc).__name__}: {core.text(exc)[:300]}")
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        attempts.append(result)
    return core.dedupe(rows), attempts


def scan_source(source: tuple) -> tuple[list[dict], dict]:
    started = time.monotonic()
    products, status = aggregate.scan_all_routes(source)
    admitted, _, _ = gate(products)
    fallback_results: list[dict] = []
    if not admitted or source[0] in CONTEXT:
        fallback, fallback_results = fallback_scan(source)
        products = core.dedupe([*products, *fallback])
    admitted, reasons, quality = gate(products)
    status = dict(status)
    route_results = list(status.get("route_results") or []) + fallback_results
    healthy_routes = [route for route in route_results if route.get("status") == "healthy"]
    status.update(
        admitted=admitted,
        status="healthy" if admitted else "quarantined",
        products=len(products),
        reason_codes=reasons,
        quality=quality,
        worker="cloud_scan_v2+html_card_fallback",
        route_results=route_results,
        routes_attempted=len(route_results),
        active_route=(max(healthy_routes, key=lambda row: int(row.get("products") or 0)).get("url", "") if healthy_routes else ""),
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return products if admitted else [], status


def run(shard: int, shards: int, output: Path, workers: int) -> int:
    selected = [source for index, source in enumerate(core.SOURCES) if index % shards == shard]
    output.mkdir(parents=True, exist_ok=True)
    products: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(selected) or 1))) as pool:
        futures = {pool.submit(scan_source, source): source[0] for source in selected}
        for future in as_completed(futures):
            source_id = futures[future]
            try:
                rows, status = future.result()
            except Exception as exc:
                rows = []
                status = {
                    "source_id": source_id,
                    "name": source_id,
                    "enabled": True,
                    "admitted": False,
                    "status": "quarantined",
                    "products": 0,
                    "reason_codes": ["worker_exception"],
                    "error": f"{type(exc).__name__}: {core.text(exc)[:500]}",
                    "quality": {"products": 0, "url_coverage": 0, "priced_products": 0},
                    "worker": "cloud_scan_v2+html_card_fallback",
                }
            products.extend(rows)
            statuses.append(status)
            print(json.dumps({"source": source_id, "status": status["status"], "products": len(rows)}), flush=True)
    payload = {
        "schema_version": "dropfinder-autonomous-shard-v1",
        "generated_at": core.now(),
        "shard": shard,
        "shards": shards,
        "products": core.dedupe(products),
        "sources": sorted(statuses, key=lambda row: str(row.get("source_id") or "")),
    }
    (output / f"shard-{shard}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def self_test() -> int:
    good = [{"url": "https://example.test/p", "price": 10}]
    assert gate(good)[0]
    assert not gate([])[0]
    assert not gate([{"url": "https://example.test/p", "price": None}])[0]
    fixture = '<a href="/products/blue-dream">Blue Dream</a><div>$24.99 Add to cart</div>'
    route = ("html", "https://example.test/collections/thca-flower", "thca_flower")
    old = CONTEXT.get("fixture")
    CONTEXT["fixture"] = "THCA Flower"
    try:
        rows = card_rows(fixture, "fixture", "Fixture", route)
        assert len(rows) == 1 and rows[0]["price"] == 24.99
    finally:
        if old is None:
            CONTEXT.pop("fixture", None)
        else:
            CONTEXT["fixture"] = old
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("scan-output"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.shards < 1 or not 0 <= args.shard < args.shards:
        parser.error("invalid shard configuration")
    return run(args.shard, args.shards, args.output, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
