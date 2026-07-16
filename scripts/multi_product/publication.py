from __future__ import annotations

import argparse
import json
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    CONTROLLED_PRODUCT_TYPES,
    ENABLED_PRODUCT_TYPES,
    PSILOCYBIN_MUSHROOM,
    PSILOCYBIN_VAPE,
)
from .classification import is_mixed_offer

SHARD_SCHEMA = "dropfinder-autonomous-shard-v1"
CATALOG_SCHEMA = "dropfinder-cloud-catalog-v4-multi-product"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _http_url(value: Any) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_shards(root: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(root.rglob("shard-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SHARD_SCHEMA:
            raise ValueError(f"unexpected shard schema: {path}")
        payloads.append(payload)
    if not payloads:
        raise RuntimeError("no worker shard results")
    return payloads


def _row_score(product: dict[str, Any]) -> tuple[int, int, str]:
    fields = (
        "price", "grams", "volume_ml", "price_per_gram", "price_per_ml",
        "thca", "psilocybin_percent", "species", "device_type", "terpenes",
        "image", "availability", "classification_evidence",
    )
    return (
        sum(product.get(field) not in (None, "", [], {}) for field in fields),
        int(product.get("completeness_score") or 0),
        str(product.get("collected_at") or ""),
    )


def dedupe(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for product in products:
        key = str(product.get("id") or "").strip()
        if not key:
            key = "|".join(
                str(product.get(field) or "").strip().casefold()
                for field in ("source_id", "primary_type", "name", "variant", "url")
            )
        if not key.strip("|"):
            continue
        current = rows.get(key)
        if current is None or _row_score(product) > _row_score(current):
            rows[key] = dict(product)
    return sorted(
        rows.values(),
        key=lambda row: (
            str(row.get("primary_type") or ""),
            str(row.get("vendor") or "").casefold(),
            str(row.get("name") or "").casefold(),
            str(row.get("id") or ""),
        ),
    )


def _classification(product: dict[str, Any]) -> tuple[str, dict[str, Any], set[str]]:
    evidence = product.get("classification_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    primary = str(product.get("primary_type") or evidence.get("primary_type") or "")
    tags_value = product.get("type_tags") or evidence.get("type_tags") or []
    tags = {str(value) for value in tags_value if str(value)}
    return primary, evidence, tags


def reject_reason(product: dict[str, Any]) -> str | None:
    name = str(product.get("name") or "").strip()
    source_id = str(product.get("source_id") or "").strip()
    vendor = str(product.get("vendor") or "").strip()
    internal_url = str(product.get("url") or "").strip()
    primary, evidence, tags = _classification(product)
    if not name:
        return "missing_name"
    if not source_id or not vendor:
        return "missing_source_identity"
    if is_mixed_offer(
        name,
        product.get("source_title"),
        product.get("variant"),
        internal_url,
        product.get("public_purchase_url"),
        product.get("route_url"),
    ):
        return "unsupported_mixed_offer"
    if not _http_url(internal_url):
        return "missing_or_invalid_internal_product_url"
    if primary not in ENABLED_PRODUCT_TYPES:
        return "unsupported_or_missing_primary_type"
    if primary not in tags:
        return "primary_type_missing_from_type_tags"
    if evidence.get("primary_type") != primary:
        return "classification_evidence_type_mismatch"
    if product.get("price") in (None, ""):
        return "missing_current_price"
    try:
        if float(product["price"]) <= 0:
            return "invalid_current_price"
    except (TypeError, ValueError):
        return "invalid_current_price"
    if product.get("availability") != "in_stock":
        return "not_explicitly_in_stock"

    if primary == CANNABIS_FLOWER:
        if not evidence.get("explicit_thca"):
            return "missing_product_level_thca_evidence"
        if not evidence.get("explicit_flower"):
            return "missing_product_level_flower_evidence"
        if evidence.get("explicit_vape"):
            return "flower_vape_contamination"
    elif primary == CANNABIS_VAPE:
        if not evidence.get("explicit_cannabis"):
            return "missing_product_level_cannabis_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
    elif primary == PSILOCYBIN_MUSHROOM:
        if not evidence.get("explicit_psilocybin"):
            return "missing_product_level_psilocybin_evidence"
        if not evidence.get("explicit_mushroom"):
            return "missing_product_level_mushroom_evidence"
        if evidence.get("explicit_vape"):
            return "mushroom_vape_contamination"
        if evidence.get("amanita_signal"):
            return "amanita_not_psilocybin"
    elif primary == PSILOCYBIN_VAPE:
        if not evidence.get("explicit_psilocybin"):
            return "missing_product_level_psilocybin_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
        if evidence.get("amanita_signal"):
            return "amanita_not_psilocybin"
    else:
        return "unsupported_primary_type"
    return None


def _public_product(product: dict[str, Any]) -> dict[str, Any]:
    row = dict(product)
    primary, evidence, tags = _classification(row)
    row["primary_type"] = primary
    row["type_tags"] = sorted(
        tags,
        key=lambda value: ENABLED_PRODUCT_TYPES.index(value) if value in ENABLED_PRODUCT_TYPES else 999,
    )
    row["classification_evidence"] = dict(evidence)
    row["classification_evidence"]["type_tags"] = list(row["type_tags"])
    row["classification_evidence"]["permits_public_purchase_link"] = primary not in CONTROLLED_PRODUCT_TYPES
    if primary in CONTROLLED_PRODUCT_TYPES:
        row["url"] = ""
        row["public_purchase_url"] = None
        row["route_url"] = ""
    else:
        public_url = str(row.get("public_purchase_url") or row.get("url") or "")
        row["url"] = public_url
        row["public_purchase_url"] = public_url
    row.pop("source_url", None)
    row.pop("raw_url", None)
    return row


def sanitize(products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for product in dedupe(products):
        reason = reject_reason(product)
        primary, _, _ = _classification(product)
        if reason:
            rejected.append({
                "source_id": product.get("source_id"),
                "vendor": product.get("vendor"),
                "name": product.get("name"),
                "url": "" if primary in CONTROLLED_PRODUCT_TYPES else product.get("url"),
                "primary_type": primary,
                "reason": reason,
            })
        else:
            accepted.append(_public_product(product))
    return dedupe(accepted), rejected


def _source_status(row: dict[str, Any], accepted_count: int, rejected_count: int) -> dict[str, Any]:
    quality = dict(row.get("quality") or {})
    quality["products"] = accepted_count
    quality["rejected_products"] = rejected_count
    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "enabled": True,
        "status": "healthy",
        "products": accepted_count,
        "active_route": row.get("active_route", ""),
        "routes_attempted": row.get("routes_attempted", 0),
        "duration_seconds": row.get("duration_seconds", 0),
        "quality": quality,
        "route_results": [route for route in row.get("route_results", []) if route.get("status") == "healthy"],
    }


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict[str, Any]:
    shards = load_shards(input_dir)
    sources = [row for payload in shards for row in payload.get("sources", [])]
    worker_active = [row for row in sources if row.get("admitted") and row.get("status") == "healthy"]
    quarantine = [row for row in sources if row not in worker_active]
    worker_active_ids = {str(row.get("source_id") or "") for row in worker_active}
    raw_products = [
        row
        for payload in shards
        for row in payload.get("products", [])
        if str(row.get("source_id") or "") in worker_active_ids
    ]
    products, rejected = sanitize(raw_products)
    counts_by_source = Counter(str(row.get("source_id") or "") for row in products)
    rejections_by_source = Counter(str(row.get("source_id") or "") for row in rejected)

    active: list[dict[str, Any]] = []
    for source in worker_active:
        source_id = str(source.get("source_id") or "")
        accepted_count = counts_by_source.get(source_id, 0)
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
            active.append(_source_status(source, accepted_count, rejections_by_source.get(source_id, 0)))

    active.sort(key=lambda row: str(row.get("name") or ""))
    quarantine.sort(key=lambda row: str(row.get("name") or ""))
    active_ids = {str(row.get("source_id") or "") for row in active}
    products = [row for row in products if str(row.get("source_id") or "") in active_ids]

    if len(active) < min_active:
        raise RuntimeError(f"active-source floor failed: {len(active)} < {min_active}")
    if len(products) < min_products:
        raise RuntimeError(f"product floor failed: {len(products)} < {min_products}")
    if any(
        row.get("primary_type") in CONTROLLED_PRODUCT_TYPES
        and (row.get("url") or row.get("public_purchase_url") or row.get("route_url"))
        for row in products
    ):
        raise RuntimeError("controlled-product purchase-link invariant failed")

    generated = now()
    type_counts = Counter(str(row.get("primary_type") or "") for row in products)
    reason_counts = dict(sorted(Counter(row["reason"] for row in rejected).items()))
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "generated_at": generated,
        "product_count": len(products),
        "products_by_type": dict(sorted(type_counts.items())),
        "enabled_product_types": list(ENABLED_PRODUCT_TYPES),
        "products": products,
    }
    status = {
        "schema_version": "dropfinder-autonomous-runtime-v3-multi-product",
        "generated_at": generated,
        "mode": "credential_free_github_actions",
        "source_count": len(sources),
        "candidate_sources": len(sources),
        "enabled_sources": len(active),
        "healthy_sources": len(active),
        "degraded_sources": 0,
        "quarantined_sources": len(quarantine),
        "healthy_routes": sum(1 for source in active for route in source.get("route_results", [])),
        "product_count": len(products),
        "products_by_type": dict(sorted(type_counts.items())),
        "rejected_products": len(rejected),
        "rejection_reasons": reason_counts,
        "services": {
            "retrieval_workers": "healthy",
            "admission_controller": "healthy",
            "product_sanitizer": "healthy",
            "catalog_merge": "healthy",
            "publisher": "healthy",
        },
        "sources": active,
        "limitations": [
            "Every active source passed retrieval, price, stock, and type-specific product evidence gates.",
            "Psilocybin records are public informational metadata with purchase links removed.",
            "Failed candidates are quarantined and retried automatically.",
        ],
    }
    quarantine_payload = {
        "schema_version": "dropfinder-source-quarantine-v3",
        "generated_at": generated,
        "count": len(quarantine),
        "sources": quarantine,
    }
    rejection_payload = {
        "schema_version": "dropfinder-product-rejections-v2-multi-product",
        "generated_at": generated,
        "count": len(rejected),
        "reason_counts": reason_counts,
        "products": rejected,
    }
    runtime = {
        "schema_version": "dropfinder-autonomous-worker-runtime-v3-multi-product",
        "generated_at": generated,
        "status": "healthy",
        "zero_degraded_active_services": True,
        "active_sources": len(active),
        "quarantined_candidates": len(quarantine),
        "products": len(products),
        "products_by_type": dict(sorted(type_counts.items())),
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


def _fixture(
    *, product_id: str, primary_type: str, name: str, url: str,
    evidence: dict[str, Any], **extra: Any,
) -> dict[str, Any]:
    return {
        "id": product_id,
        "source_id": "a",
        "vendor": "Vendor A",
        "primary_type": primary_type,
        "type_tags": [primary_type],
        "name": name,
        "url": url,
        "public_purchase_url": url,
        "price": 20,
        "availability": "in_stock",
        "classification_evidence": {"primary_type": primary_type, "type_tags": [primary_type], **evidence},
        **extra,
    }


def self_test(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    flower = _fixture(
        product_id="flower", primary_type=CANNABIS_FLOWER,
        name="Blue Dream THCA Flower", url="https://example.test/products/flower",
        evidence={"explicit_thca": True, "explicit_flower": True, "explicit_vape": False},
    )
    vape = _fixture(
        product_id="vape", primary_type=CANNABIS_VAPE,
        name="THCA Disposable Vape 1mL", url="https://example.test/products/vape",
        evidence={"explicit_cannabis": True, "explicit_vape": True},
        volume_ml=1, price_per_ml=20,
    )
    mushroom = _fixture(
        product_id="mushroom", primary_type=PSILOCYBIN_MUSHROOM,
        name="Psilocybe Cubensis Psilocybin Mushrooms 7g",
        url="https://example.test/products/mushroom",
        evidence={
            "explicit_psilocybin": True, "explicit_mushroom": True,
            "explicit_vape": False, "amanita_signal": False,
        },
        grams=7, price_per_gram=2.8571,
    )
    amanita = _fixture(
        product_id="amanita", primary_type=PSILOCYBIN_MUSHROOM,
        name="Amanita Mushroom 7g", url="https://example.test/products/amanita",
        evidence={
            "explicit_psilocybin": False, "explicit_mushroom": True,
            "explicit_vape": False, "amanita_signal": True,
        },
    )
    (root / "shard-0.json").write_text(
        json.dumps({
            "schema_version": SHARD_SCHEMA,
            "products": [flower, vape, mushroom, amanita],
            "sources": [{"source_id": "a", "name": "A", "admitted": True, "status": "healthy", "products": 4}],
        }),
        encoding="utf-8",
    )
    runtime = merge(root, root / "out", 1, 1)
    catalog = json.loads((root / "out" / "catalog.json").read_text(encoding="utf-8"))
    rejections = json.loads((root / "out" / "rejections.json").read_text(encoding="utf-8"))
    assert runtime["zero_degraded_active_services"]
    assert catalog["product_count"] == 3
    assert catalog["products_by_type"] == {
        CANNABIS_FLOWER: 1,
        CANNABIS_VAPE: 1,
        PSILOCYBIN_MUSHROOM: 1,
    }
    controlled = next(row for row in catalog["products"] if row["id"] == "mushroom")
    assert controlled["url"] == ""
    assert controlled["public_purchase_url"] is None
    assert rejections["count"] == 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("cloud_pages/data"))
    parser.add_argument("--min-active", type=int, default=5)
    parser.add_argument("--min-products", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(Path("/tmp/dropfinder-autonomous-merge-test"))
    if args.input is None:
        parser.error("--input is required")
    merge(args.input, args.output, args.min_active, args.min_products)
    return 0
