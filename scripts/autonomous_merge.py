#!/usr/bin/env python3
"""Publish only complete, product-level THCA flower comparison records."""
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FORBIDDEN = re.compile(
    r"\b(?:pre[- ]?rolls?|prerolls?|joints?|blunts?|cones?|vapes?|cartridges?|carts?|"
    r"disposables?|gumm(?:y|ies)|edibles?|tinctures?|capsules?|beverages?|drinks?|"
    r"seltzers?|concentrates?|rosin|resin|badder|budder|crumble|isolate|dabs?|wax|"
    r"sift\s*pucks?|pucks?|seeds?|clones?|incense|topicals?|salves?|balms?|"
    r"creams?|lotions?|apparel|shirts?|hoodies?|hats?|posters?|fertilizer|accessories?|"
    r"grinders?|trays?|glass|mushrooms?|amanita|pets?|gift\s*cards?|subscriptions?|"
    r"samplers?|mystery\s*(?:box|bag|pack)s?|wholesale|bundles?|hash\s*holes?)\b",
    re.I,
)
AMBIGUOUS_HASH = re.compile(r"\bhash\b", re.I)
THCA = re.compile(r"\b(?:thca|thc-a|high\s+thca)\b", re.I)
FLOWER = re.compile(r"\b(?:flower|buds?|smalls?|minis?|popcorn|shake|trim)\b", re.I)
ALT = re.compile(r"\b(?:cbd|cbg|type\s*[34]|delta[- ]?8|hhc|thc[- ]?p|thc[- ]?o)\b", re.I)
PLACEHOLDER = re.compile(r"^(?:product|flower|strain|indica|sativa|hybrid|indica[, /]+hybrid[, /]+sativa|unknown|untitled)$", re.I)
EXACT_PRICING = {"exact_variant", "exact_title"}
KNOWN_STOCK = {"in_stock", "out_of_stock"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def positive(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def load_shards(root: Path) -> list[dict]:
    payloads = []
    for path in sorted(root.rglob("shard-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "dropfinder-autonomous-shard-v1":
            raise ValueError(f"unexpected shard schema: {path}")
        payloads.append(payload)
    if not payloads:
        raise RuntimeError("no worker shard results")
    return payloads


def completeness_score(product: dict) -> int:
    return sum(
        product.get(field) not in (None, "", [], {})
        for field in (
            "price",
            "grams",
            "price_per_gram",
            "thca",
            "image",
            "availability",
            "pricing_confidence",
            "classification_evidence",
        )
    )


def dedupe(products: list[dict]) -> list[dict]:
    rows: dict[str, dict] = {}
    for product in products:
        key = str(product.get("id") or product.get("url") or "").strip()
        if not key:
            continue
        current = rows.get(key)
        if current is None or completeness_score(product) > completeness_score(current):
            rows[key] = product
    return sorted(rows.values(), key=lambda row: (str(row.get("vendor") or "").lower(), str(row.get("name") or "").lower()))


def product_text(product: dict) -> str:
    url = str(product.get("url") or "")
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).replace("-", " ").replace("_", " ")
    except ValueError:
        path = url
    return " ".join(str(product.get(field) or "") for field in ("name", "variant")) + " " + path


def comparison_reject_reason(product: dict) -> str | None:
    price = positive(product.get("price"))
    grams = positive(product.get("grams"))
    price_per_gram = positive(product.get("price_per_gram"))
    thca = positive(product.get("thca"))
    if price is None:
        return "missing_exact_price"
    if grams is None:
        return "missing_exact_grams"
    if product.get("pricing_confidence") not in EXACT_PRICING:
        return "unpaired_price_and_weight"
    if product.get("weight_source") not in {"variant", "title"}:
        return "untrusted_weight_source"
    if price_per_gram is None:
        return "missing_price_per_gram"
    calculated = round(price / grams, 4)
    if abs(calculated - price_per_gram) > max(0.02, calculated * 0.01):
        return "price_per_gram_mismatch"
    if not 0.1 <= price_per_gram <= 500:
        return "implausible_price_per_gram"
    if thca is None or thca > 100:
        return "missing_verified_thca_percentage"
    if product.get("availability") not in KNOWN_STOCK:
        return "unknown_availability"
    image = str(product.get("image") or "").strip()
    if not image.startswith(("http://", "https://")):
        return "missing_product_image"
    return None


def reject_reason(product: dict) -> str | None:
    name = str(product.get("name") or "").strip()
    url = str(product.get("url") or "").strip()
    text = product_text(product)
    evidence = product.get("classification_evidence") if isinstance(product.get("classification_evidence"), dict) else {}
    explicit_thca = bool(evidence.get("explicit_thca")) or bool(THCA.search(text))
    explicit_flower = bool(evidence.get("explicit_flower")) or bool(FLOWER.search(text))
    if not name:
        return "missing_name"
    if not url.startswith(("http://", "https://")):
        return "missing_or_invalid_url"
    if FORBIDDEN.search(text):
        return "forbidden_product_form"
    if AMBIGUOUS_HASH.search(text) and not explicit_flower:
        return "ambiguous_hash_without_flower_evidence"
    if PLACEHOLDER.fullmatch(name):
        return "generic_or_fragment_title"
    if ALT.search(text) and not explicit_thca:
        return "alternate_cannabinoid_without_thca"
    if not explicit_thca:
        return "missing_product_level_thca_evidence"
    if not explicit_flower:
        return "missing_product_level_flower_evidence"
    if product.get("availability") == "out_of_stock" and product.get("price") in (None, "") and not product.get("image"):
        return "out_of_stock_placeholder_without_product_data"
    return comparison_reject_reason(product)


def sanitize(products: list[dict]) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    for product in dedupe(products):
        reason = reject_reason(product)
        if reason:
            rejected.append({
                "id": product.get("id"),
                "source_id": product.get("source_id"),
                "vendor": product.get("vendor"),
                "name": product.get("name"),
                "variant": product.get("variant"),
                "url": product.get("url"),
                "price": product.get("price"),
                "grams": product.get("grams"),
                "price_per_gram": product.get("price_per_gram"),
                "thca": product.get("thca"),
                "availability": product.get("availability"),
                "reason": reason,
            })
        else:
            row = dict(product)
            row["comparison_complete"] = True
            row["comparison_contract"] = "exact_price_weight_ppg_thca_stock_image_v1"
            accepted.append(row)
    return dedupe(accepted), rejected


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict:
    shards = load_shards(input_dir)
    sources = [row for payload in shards for row in payload.get("sources", [])]
    worker_active = [row for row in sources if row.get("admitted") and row.get("status") == "healthy"]
    worker_quarantine = [row for row in sources if row not in worker_active]
    worker_active_ids = {str(row.get("source_id") or "") for row in worker_active}
    raw_products = [row for payload in shards for row in payload.get("products", []) if str(row.get("source_id") or "") in worker_active_ids]
    products, rejected = sanitize(raw_products)
    counts = Counter(str(row.get("source_id") or "") for row in products)

    active: list[dict] = []
    quarantine = list(worker_quarantine)
    for source in worker_active:
        source_id = str(source.get("source_id") or "")
        accepted_count = counts.get(source_id, 0)
        if accepted_count <= 0:
            quarantined = dict(source)
            quarantined.update(
                admitted=False,
                status="quarantined",
                products=0,
                reason_codes=sorted(set([*(source.get("reason_codes") or []), "no_complete_products_after_final_sanitizer"])),
            )
            quarantine.append(quarantined)
        else:
            admitted = dict(source)
            quality = dict(admitted.get("quality") or {})
            quality["products"] = accepted_count
            quality["complete_products"] = accepted_count
            quality["rejected_products"] = sum(1 for row in rejected if str(row.get("source_id") or "") == source_id)
            admitted.update(products=accepted_count, quality=quality, admitted=True, status="healthy")
            active.append(admitted)

    active = sorted(active, key=lambda row: str(row.get("name") or ""))
    quarantine = sorted(quarantine, key=lambda row: str(row.get("name") or ""))
    active_ids = {str(row.get("source_id") or "") for row in active}
    products = [row for row in products if str(row.get("source_id") or "") in active_ids]

    if len(active) < min_active:
        raise RuntimeError(f"active-source floor failed: {len(active)} < {min_active}")
    if len(products) < min_products:
        raise RuntimeError(f"complete-product floor failed: {len(products)} < {min_products}")
    if any(reject_reason(product) for product in products):
        raise RuntimeError("final complete-product sanitizer invariant failed")

    generated = now()
    catalog = {
        "schema_version": "dropfinder-cloud-catalog-v4",
        "generated_at": generated,
        "comparison_contract": "exact_price_weight_ppg_thca_stock_image_v1",
        "product_count": len(products),
        "products": products,
    }
    status_sources = [
        {
            "source_id": row.get("source_id"),
            "name": row.get("name"),
            "enabled": True,
            "status": "healthy",
            "products": row.get("products", 0),
            "active_route": row.get("active_route", ""),
            "routes_attempted": row.get("routes_attempted", 0),
            "duration_seconds": row.get("duration_seconds", 0),
            "quality": row.get("quality", {}),
            "route_results": [route for route in row.get("route_results", []) if route.get("status") == "healthy"],
        }
        for row in active
    ]
    reason_counts = dict(sorted(Counter(row["reason"] for row in rejected).items()))
    status = {
        "schema_version": "dropfinder-autonomous-runtime-v3",
        "generated_at": generated,
        "mode": "credential_free_github_actions",
        "comparison_contract": "exact_price_weight_ppg_thca_stock_image_v1",
        "source_count": len(sources),
        "candidate_sources": len(sources),
        "enabled_sources": len(active),
        "healthy_sources": len(active),
        "degraded_sources": 0,
        "quarantined_sources": len(quarantine),
        "healthy_routes": sum(1 for source in status_sources for route in source.get("route_results", [])),
        "product_count": len(products),
        "complete_products": len(products),
        "rejected_products": len(rejected),
        "rejection_reasons": reason_counts,
        "services": {
            "retrieval_workers": "healthy",
            "admission_controller": "healthy",
            "product_sanitizer": "healthy",
            "comparison_completeness_gate": "healthy",
            "catalog_merge": "healthy",
            "publisher": "healthy",
        },
        "sources": status_sources,
        "limitations": [
            "Only exact purchasable variants with verified THCA percentage, grams, price per gram, stock, and image are published.",
            "Incomplete or contradictory candidates are automatically rejected fail-closed and retained in rejection evidence.",
            "Failed source candidates are quarantined and retried automatically; they are not counted as degraded active services.",
        ],
    }
    quarantine_payload = {
        "schema_version": "dropfinder-source-quarantine-v3",
        "generated_at": generated,
        "count": len(quarantine),
        "sources": quarantine,
    }
    rejection_payload = {
        "schema_version": "dropfinder-product-rejections-v2",
        "generated_at": generated,
        "count": len(rejected),
        "reason_counts": reason_counts,
        "products": rejected,
    }
    runtime = {
        "schema_version": "dropfinder-autonomous-worker-runtime-v3",
        "generated_at": generated,
        "status": "healthy",
        "zero_degraded_active_services": True,
        "comparison_contract": "exact_price_weight_ppg_thca_stock_image_v1",
        "active_sources": len(active),
        "quarantined_candidates": len(quarantine),
        "products": len(products),
        "complete_products": len(products),
        "rejected_products": len(rejected),
        "shards": len(shards),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("catalog.json", catalog),
        ("status.json", status),
        ("quarantine.json", quarantine_payload),
        ("rejections.json", rejection_payload),
        ("runtime.json", runtime),
    ):
        (output_dir / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return runtime


def complete_fixture(product_id: str, name: str, price: float) -> dict:
    grams = 3.5
    return {
        "id": product_id,
        "source_id": "a",
        "vendor": "A",
        "name": name,
        "variant": "3.5g",
        "url": f"https://x/products/{product_id}",
        "image": f"https://x/images/{product_id}.jpg",
        "price": price,
        "grams": grams,
        "price_per_gram": round(price / grams, 4),
        "pricing_confidence": "exact_variant",
        "weight_source": "variant",
        "thca": 27.4,
        "availability": "in_stock",
        "classification_evidence": {"explicit_thca": True, "explicit_flower": True},
    }


def self_test(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    valid = complete_fixture("1", "Blue Dream THCA Flower 3.5g", 20)
    valid_hash_strain = complete_fixture("4", "Hash Burger THCA Flower 3.5g", 25)
    bad_roll = complete_fixture("2", "Indica THCA Pre-Rolled Joints 3.5g", 10)
    bad_subscription = complete_fixture("3", "THCA Flower Subscription 3.5g", 20)
    incomplete = complete_fixture("5", "Incomplete THCA Flower 3.5g", 20)
    incomplete["thca"] = None
    (root / "shard-0.json").write_text(json.dumps({
        "schema_version": "dropfinder-autonomous-shard-v1",
        "products": [valid, valid_hash_strain, bad_roll, bad_subscription, incomplete],
        "sources": [
            {"source_id": "a", "name": "A", "admitted": True, "status": "healthy", "products": 5},
            {"source_id": "b", "name": "B", "admitted": False, "status": "quarantined", "products": 0},
        ],
    }), encoding="utf-8")
    runtime = merge(root, root / "out", 1, 1)
    status = json.loads((root / "out" / "status.json").read_text())
    catalog = json.loads((root / "out" / "catalog.json").read_text())
    rejections = json.loads((root / "out" / "rejections.json").read_text())
    assert runtime["zero_degraded_active_services"] and status["degraded_sources"] == 0
    assert catalog["product_count"] == 2
    assert all(row["comparison_complete"] for row in catalog["products"])
    assert {row["id"] for row in catalog["products"]} == {"1", "4"}
    assert rejections["count"] == 3
    assert rejections["reason_counts"]["missing_verified_thca_percentage"] == 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-active", type=int, default=5)
    parser.add_argument("--min-products", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            return self_test(Path(temporary))
    if not args.input or not args.output:
        parser.error("--input and --output are required")
    merge(args.input, args.output, args.min_active, args.min_products)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
