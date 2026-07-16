#!/usr/bin/env python3
"""Admit healthy retrieval workers and publish a zero-degraded typed catalog."""
from __future__ import annotations

import argparse
import json
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


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def dedupe(products: list[dict]) -> list[dict]:
    rows: dict[str, dict] = {}
    for product in products:
        key = str(product.get("id") or product.get("url") or "").strip()
        if not key:
            continue
        current = rows.get(key)
        score = sum(
            product.get(field) not in (None, "", [], {})
            for field in ("price", "grams", "thca", "image", "availability", "classification_evidence")
        )
        old_score = -1 if current is None else sum(
            current.get(field) not in (None, "", [], {})
            for field in ("price", "grams", "thca", "image", "availability", "classification_evidence")
        )
        if current is None or score > old_score:
            rows[key] = product
    return sorted(
        rows.values(),
        key=lambda row: (str(row.get("vendor") or "").lower(), str(row.get("name") or "").lower()),
    )


def product_text(product: dict) -> str:
    url = str(product.get("url") or "")
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).replace("-", " ").replace("_", " ")
    except ValueError:
        path = url
    return " ".join(str(product.get(field) or "") for field in ("name", "variant")) + " " + path


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
    return None


def sanitize(products: list[dict]) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    for product in dedupe(products):
        reason = reject_reason(product)
        if reason:
            rejected.append({
                "source_id": product.get("source_id"),
                "vendor": product.get("vendor"),
                "name": product.get("name"),
                "url": product.get("url"),
                "reason": reason,
            })
        else:
            accepted.append(product)
    return dedupe(accepted), rejected


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict:
    shards = load_shards(input_dir)
    sources = [row for payload in shards for row in payload.get("sources", [])]
    worker_active = [row for row in sources if row.get("admitted") and row.get("status") == "healthy"]
    worker_quarantine = [row for row in sources if row not in worker_active]
    worker_active_ids = {str(row.get("source_id") or "") for row in worker_active}
    raw_products = [
        row
        for payload in shards
        for row in payload.get("products", [])
        if str(row.get("source_id") or "") in worker_active_ids
    ]
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
                reason_codes=sorted(set([*(source.get("reason_codes") or []), "no_products_after_final_sanitizer"])),
            )
            quarantine.append(quarantined)
        else:
            admitted = dict(source)
            quality = dict(admitted.get("quality") or {})
            quality["products"] = accepted_count
            quality["rejected_products"] = sum(
                1 for row in rejected if str(row.get("source_id") or "") == source_id
            )
            admitted.update(products=accepted_count, quality=quality, admitted=True, status="healthy")
            active.append(admitted)

    active = sorted(active, key=lambda row: str(row.get("name") or ""))
    quarantine = sorted(quarantine, key=lambda row: str(row.get("name") or ""))
    active_ids = {str(row.get("source_id") or "") for row in active}
    products = [row for row in products if str(row.get("source_id") or "") in active_ids]

    if len(active) < min_active:
        raise RuntimeError(f"active-source floor failed: {len(active)} < {min_active}")
    if len(products) < min_products:
        raise RuntimeError(f"product floor failed: {len(products)} < {min_products}")
    if any(reject_reason(product) for product in products):
        raise RuntimeError("final product sanitizer invariant failed")

    generated = now()
    type_counts = dict(sorted(Counter(str(row.get("product_type") or "cannabis_flower") for row in products).items()))
    catalog = {
        "schema_version": "dropfinder-cloud-catalog-v3",
        "generated_at": generated,
        "product_count": len(products),
        "product_type_counts": type_counts,
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
        "schema_version": "dropfinder-autonomous-runtime-v2",
        "generated_at": generated,
        "mode": "credential_free_github_actions",
        "source_count": len(sources),
        "candidate_sources": len(sources),
        "enabled_sources": len(active),
        "healthy_sources": len(active),
        "degraded_sources": 0,
        "quarantined_sources": len(quarantine),
        "healthy_routes": sum(1 for source in status_sources for route in source.get("route_results", [])),
        "product_count": len(products),
        "product_type_counts": type_counts,
        "rejected_products": len(rejected),
        "rejection_reasons": reason_counts,
        "services": {
            "retrieval_workers": "healthy",
            "admission_controller": "healthy",
            "product_sanitizer": "healthy",
            "catalog_merge": "healthy",
            "publisher": "healthy",
        },
        "sources": status_sources,
        "limitations": [
            "Every active source passed retrieval, data-quality, and final product-level evidence gates.",
            "Failed candidates are quarantined and retried automatically; they are not counted as degraded active services.",
            "Workers run as scheduled resumable GitHub Actions jobs rather than permanent daemons.",
        ],
    }
    quarantine_payload = {
        "schema_version": "dropfinder-source-quarantine-v2",
        "generated_at": generated,
        "count": len(quarantine),
        "sources": quarantine,
    }
    rejection_payload = {
        "schema_version": "dropfinder-product-rejections-v1",
        "generated_at": generated,
        "count": len(rejected),
        "reason_counts": reason_counts,
        "products": rejected,
    }
    runtime = {
        "schema_version": "dropfinder-autonomous-worker-runtime-v2",
        "generated_at": generated,
        "status": "healthy",
        "zero_degraded_active_services": True,
        "active_sources": len(active),
        "quarantined_candidates": len(quarantine),
        "products": len(products),
        "product_type_counts": type_counts,
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
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return runtime


# Replace the historical flower-only sanitizer with the explicit type-aware
# policy. The import works both when this file is executed directly and when it
# is imported as scripts.autonomous_merge.
try:
    from multi_product import install_merge as _install_multi_product_merge
except ImportError:  # pragma: no cover - package import path
    from scripts.multi_product import install_merge as _install_multi_product_merge
_install_multi_product_merge(globals())


def self_test(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    valid = {
        "id": "1",
        "source_id": "a",
        "name": "Blue Dream THCA Flower",
        "url": "https://x/products/blue-dream-thca-flower",
        "price": 20,
        "product_type": "cannabis_flower",
        "classification_evidence": {
            "product_type": "cannabis_flower",
            "explicit_thca": True,
            "explicit_flower": True,
        },
    }
    valid_hash_strain = {
        "id": "4",
        "source_id": "a",
        "name": "Hash Burger THCA Flower",
        "url": "https://x/products/hash-burger-thca-flower",
        "price": 25,
        "product_type": "cannabis_flower",
        "classification_evidence": {
            "product_type": "cannabis_flower",
            "explicit_thca": True,
            "explicit_flower": True,
        },
    }
    valid_vape = {
        "id": "5",
        "source_id": "a",
        "name": "Blue Dream THCA Disposable Vape 1g",
        "url": "https://x/products/blue-dream-thca-vape",
        "price": 30,
        "grams": 1,
        "availability": "in_stock",
        "product_type": "cannabis_vape",
        "classification_evidence": {
            "product_type": "cannabis_vape",
            "explicit_thca": True,
            "explicit_vape": True,
        },
    }
    valid_mushroom = {
        "id": "6",
        "source_id": "a",
        "name": "Amanita Mushroom Caps 7g",
        "url": "https://x/products/amanita-mushroom-caps",
        "price": 24,
        "grams": 7,
        "availability": "in_stock",
        "product_type": "mushroom",
        "classification_evidence": {
            "product_type": "mushroom",
            "explicit_mushroom": True,
        },
    }
    bad_roll = {
        "id": "2",
        "source_id": "a",
        "name": "Indica Hybrid Sativa",
        "url": "https://x/products/thca-pre-rolled-joints",
        "price": 10,
    }
    bad_subscription = {
        "id": "3",
        "source_id": "a",
        "name": "THCA Flower Subscription",
        "url": "https://x/products/subscription",
        "price": 20,
    }
    bad_nicotine = {
        "id": "7",
        "source_id": "a",
        "name": "Nicotine Disposable Vape",
        "url": "https://x/products/nicotine-vape",
        "price": 20,
        "product_type": "cannabis_vape",
        "classification_evidence": {
            "product_type": "cannabis_vape",
            "explicit_vape": True,
            "explicit_thca": False,
        },
    }
    (root / "shard-0.json").write_text(
        json.dumps({
            "schema_version": "dropfinder-autonomous-shard-v1",
            "products": [
                valid,
                valid_hash_strain,
                valid_vape,
                valid_mushroom,
                bad_roll,
                bad_subscription,
                bad_nicotine,
            ],
            "sources": [
                {"source_id": "a", "name": "A", "admitted": True, "status": "healthy", "products": 7},
                {"source_id": "b", "name": "B", "admitted": False, "status": "quarantined", "products": 0},
            ],
        }),
        encoding="utf-8",
    )
    runtime = merge(root, root / "out", 1, 1)
    status = json.loads((root / "out" / "status.json").read_text())
    catalog = json.loads((root / "out" / "catalog.json").read_text())
    rejections = json.loads((root / "out" / "rejections.json").read_text())
    assert runtime["zero_degraded_active_services"] and status["degraded_sources"] == 0
    assert catalog["product_count"] == 4
    assert {row["id"] for row in catalog["products"]} == {"1", "4", "5", "6"}
    assert catalog["product_type_counts"] == {
        "cannabis_flower": 2,
        "cannabis_vape": 1,
        "mushroom": 1,
    }
    assert rejections["count"] == 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("scan-results"))
    parser.add_argument("--output", type=Path, default=Path("cloud_pages/data"))
    parser.add_argument("--min-active", type=int, default=5)
    parser.add_argument("--min-products", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(Path("/tmp/dropfinder-autonomous-merge-test"))
    runtime = merge(args.input, args.output, args.min_active, args.min_products)
    print(json.dumps(runtime, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
