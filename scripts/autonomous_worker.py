#!/usr/bin/env python3
"""Run strict product-level storefront retrieval workers on GitHub Actions shards."""
from __future__ import annotations

import argparse
import hashlib
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
FALLBACK_EXCLUDE = re.compile(
    r"\b(?:sift\s*pucks?|dry\s*sift|pucks?|hash\s*holes?|pre[- ]?rolls?|prerolls?|"
    r"joints?|blunts?|cones?|seeds?|subscriptions?|samplers?|mystery\s*(?:box|bag|pack)s?|"
    r"wholesale|bundles?)\b",
    re.I,
)
FALLBACK_HTML_ROUTES = {
    "black_tie_cbd": ["https://www.blacktiecbd.net/collections/thca-flower"],
    "preston_herb_co": ["https://www.prestonherbco.com/categories/flower"],
    "holy_city_farms": ["https://holycityfarms.com/product-tag/thca/"],
    "wnc_cbd": ["https://wnc-cbd.com/high-thca-flower"],
    "secret_nature": [
        "https://secretnature.com/collections/thca-flower",
        "https://secretnaturecbd.com/collections/thca-flower",
    ],
}


def path_text(target: str) -> str:
    try:
        return urllib.parse.unquote(urllib.parse.urlsplit(target).path).replace("-", " ").replace("_", " ")
    except ValueError:
        return target


def has_product_evidence(value: str) -> bool:
    value = core.text(value)
    return bool(core.THCA.search(value) and core.FLOWER.search(value) and not core.HARD_EXCLUDE.search(value) and not FALLBACK_EXCLUDE.search(value))


def evidence_payload(value: str, source: str) -> dict:
    normalized = core.text(value)
    return {
        "explicit_thca": bool(core.THCA.search(normalized)),
        "explicit_flower": bool(core.FLOWER.search(normalized)),
        "evidence_source": source,
        "evidence_sha256": hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest(),
    }


def product_detail_evidence(payload: str, target: str) -> str:
    parts: list[str] = []
    meta = core.meta_values(payload)
    for key in ("og:title", "twitter:title", "og:description", "twitter:description", "description", "product:category"):
        if meta.get(key):
            parts.append(str(meta[key]))
    title_match = core.TITLE.search(payload)
    if title_match:
        parts.append(core.text(title_match.group(1)))
    for raw in core.LD.findall(payload):
        try:
            data = json.loads(core.html.unescape(raw.strip()))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        for item in core.objects(data):
            kind = item.get("@type")
            kinds = {str(value).lower() for value in (kind if isinstance(kind, list) else [kind])}
            if "product" not in kinds:
                continue
            for key in ("name", "description", "category", "sku", "productID"):
                if item.get(key):
                    parts.append(str(item[key]))
    parts.append(path_text(target))
    return core.text(" ".join(parts))


def decorate(product: dict, evidence: str, source: str) -> dict:
    row = dict(product)
    row["classification_evidence"] = evidence_payload(evidence, source)
    return row


def verify_existing_product(product: dict, source_id: str, vendor: str) -> dict | None:
    target = str(product.get("url") or "")
    direct = core.text(f"{product.get('name', '')} {product.get('variant', '')} {path_text(target)}")
    if has_product_evidence(direct):
        return decorate(product, direct, "product_title_or_url")
    try:
        payload, content_type, status = core.fetch(target)
    except Exception:
        return None
    if status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return None
    evidence = product_detail_evidence(payload, target)
    if not has_product_evidence(evidence):
        return None
    return decorate(product, evidence, "product_detail_metadata")


def verify_products(products: list[dict], source_id: str, vendor: str) -> list[dict]:
    direct: list[dict] = []
    unresolved: list[dict] = []
    for product in core.dedupe(products):
        value = core.text(f"{product.get('name', '')} {product.get('variant', '')} {path_text(str(product.get('url') or ''))}")
        if has_product_evidence(value):
            direct.append(decorate(product, value, "product_title_or_url"))
        else:
            unresolved.append(product)
    verified = list(direct)
    if unresolved:
        with ThreadPoolExecutor(max_workers=min(8, len(unresolved))) as pool:
            futures = {pool.submit(verify_existing_product, product, source_id, vendor): product for product in unresolved}
            for future in as_completed(futures):
                try:
                    row = future.result()
                except Exception:
                    row = None
                if row:
                    verified.append(row)
    return core.dedupe(verified)


def gate(products: list[dict]) -> tuple[bool, list[str], dict]:
    reasons: list[str] = []
    count = len(products)
    valid_urls = sum(bool(str(row.get("url") or "").strip()) for row in products)
    priced = sum(core.num(row.get("price")) is not None for row in products)
    evidenced = sum(
        isinstance(row.get("classification_evidence"), dict)
        and row["classification_evidence"].get("explicit_thca")
        and row["classification_evidence"].get("explicit_flower")
        for row in products
    )
    if count == 0:
        reasons.append("no_qualifying_products")
    if count and valid_urls / count < 0.90:
        reasons.append("insufficient_product_urls")
    if count and priced == 0:
        reasons.append("no_priced_products")
    if count and evidenced != count:
        reasons.append("missing_product_level_evidence")
    return not reasons, reasons, {
        "products": count,
        "url_coverage": round(valid_urls / count, 4) if count else 0,
        "priced_products": priced,
        "evidenced_products": evidenced,
    }


def card_candidates(payload: str, route: tuple) -> list[dict]:
    base_host = urllib.parse.urlsplit(route[1]).netloc.lower()
    candidates: dict[str, dict] = {}
    for match in core.ANCHOR.finditer(payload):
        target = core.url(match.group(1), route[1])
        parsed = urllib.parse.urlsplit(target)
        if not target or parsed.netloc.lower() != base_host:
            continue
        path = parsed.path.lower()
        if not any(marker in path for marker in PRODUCT_PATHS):
            continue
        label = core.text(match.group(2))
        if len(label) < 4 or label.lower() in {"options", "view product", "learn more", "shop now", "add to cart"}:
            continue
        form_text = f"{label} {path_text(target)}"
        if core.HARD_EXCLUDE.search(form_text) or FALLBACK_EXCLUDE.search(form_text):
            continue
        nearby = core.text(payload[match.start() : min(len(payload), match.end() + 2200)])
        prices = [core.num(value) for value in PRICE.findall(nearby)]
        price = next((value for value in prices if value is not None), None)
        stock = "out_of_stock" if "out of stock" in nearby.lower() else "in_stock" if any(token in nearby.lower() for token in ("add to cart", "choose an option", "in stock")) else ""
        current = candidates.get(target)
        candidate = {"name": label, "url": target, "price": price, "stock": stock, "card_evidence": form_text}
        if current is None or (current.get("price") is None and price is not None):
            candidates[target] = candidate
    return list(candidates.values())[:120]


def candidate_to_row(candidate: dict, source_id: str, vendor: str) -> dict | None:
    target = str(candidate["url"])
    direct = str(candidate.get("card_evidence") or "")
    detail_route = ("html", target, "product_detail")
    if has_product_evidence(direct):
        row = core.record(source_id, vendor, detail_route, candidate.get("name"), target, path_text(target), candidate.get("price"), candidate.get("stock"))
        return decorate(row, direct, "product_card_title_or_url") if row else None
    try:
        payload, content_type, status = core.fetch(target)
    except Exception:
        return None
    if status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return None
    evidence = product_detail_evidence(payload, target)
    if not has_product_evidence(evidence):
        return None
    meta = core.meta_values(payload)
    title = meta.get("og:title") or meta.get("twitter:title") or candidate.get("name")
    price = meta.get("product:price:amount") or meta.get("og:price:amount") or candidate.get("price")
    stock = meta.get("product:availability") or candidate.get("stock")
    image = meta.get("og:image") or meta.get("twitter:image") or ""
    row = core.record(source_id, vendor, detail_route, title, target, evidence, price, stock, image)
    return decorate(row, evidence, "product_detail_metadata") if row else None


def fallback_scan(source: tuple) -> tuple[list[dict], list[dict]]:
    source_id, vendor, _ = source
    targets = FALLBACK_HTML_ROUTES.get(source_id, [])
    rows: list[dict] = []
    attempts: list[dict] = []
    for index, target in enumerate(targets, 1):
        route = ("html", target, "thca_flower")
        started = time.monotonic()
        result = {
            "route_id": f"{source_id}-fallback-{index}",
            "url": target,
            "source_type": "html_card_product_detail",
        }
        try:
            payload, content_type, http_status = core.fetch(target)
            candidates = card_candidates(payload, route)
            extracted: list[dict] = []
            if candidates:
                with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
                    futures = {pool.submit(candidate_to_row, candidate, source_id, vendor): candidate for candidate in candidates}
                    for future in as_completed(futures):
                        try:
                            row = future.result()
                        except Exception:
                            row = None
                        if row:
                            extracted.append(row)
            extracted = core.dedupe(extracted)
            result.update(
                http_status=http_status,
                content_type=content_type,
                status="healthy" if extracted else "empty",
                candidates=len(candidates),
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
    source_id, vendor, _ = source
    raw_products, status = aggregate.scan_all_routes(source)
    products = verify_products(raw_products, source_id, vendor)
    fallback_results: list[dict] = []
    if source_id in FALLBACK_HTML_ROUTES:
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
        worker="cloud_scan_v2+product_detail_verifier",
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
                    "quality": {"products": 0, "url_coverage": 0, "priced_products": 0, "evidenced_products": 0},
                    "worker": "cloud_scan_v2+product_detail_verifier",
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
    explicit = "Blue Dream THCA Flower /products/blue-dream-thca-flower"
    assert has_product_evidence(explicit)
    assert not has_product_evidence("THCA Pre-Rolled Joints /products/thca-pre-roll")
    fixture = '''
    <html><head>
      <meta property="og:title" content="Blue Dream THCA Flower">
      <meta name="description" content="Loose indoor THCA flower buds">
    </head><body></body></html>
    '''
    evidence = product_detail_evidence(fixture, "https://example.test/products/blue-dream")
    assert has_product_evidence(evidence)
    good = [{"url": "https://example.test/products/blue-dream-thca-flower", "price": 10, "classification_evidence": evidence_payload(explicit, "test")}]
    assert gate(good)[0]
    assert not gate([])[0]
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("scan-output"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.shards < 1 or not 0 <= args.shard < args.shards:
        parser.error("invalid shard configuration")
    return run(args.shard, args.shards, args.output, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
