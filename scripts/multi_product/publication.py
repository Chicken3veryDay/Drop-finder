from __future__ import annotations

import argparse
import json
import math
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


def _positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _vape_quantity_reject_reason(product: dict[str, Any]) -> str | None:
    unit = str(product.get("quantity_unit") or "")
    grams = _positive_number(product.get("grams"))
    volume_ml = _positive_number(product.get("volume_ml"))
    quantity_value = _positive_number(product.get("quantity_value"))
    metric = str(product.get("comparison_metric") or "")
    comparison = _positive_number(product.get("comparison_price"))
    price_per_ml = _positive_number(product.get("price_per_ml"))
    current_price = _positive_number(product.get("price"))

    if unit == "g" or grams is not None:
        return "unsupported_vape_mass_quantity"
    if unit != "ml" or volume_ml is None:
        return "missing_vape_volume"
    if quantity_value is not None and abs(quantity_value - volume_ml) > 0.0001:
        return "inconsistent_vape_quantity"
    if metric != "price_per_ml" or comparison is None or price_per_ml is None:
        return "missing_vape_comparison_price"
    expected = current_price / volume_ml if current_price is not None else None
    if (
        abs(comparison - price_per_ml) > 0.0001
        or expected is None
        or abs(price_per_ml - expected) > 0.0001
    ):
        return "inconsistent_vape_comparison_price"
    return None


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
        quantity_reason = _vape_quantity_reject_reason(product)
        if quantity_reason:
            return quantity_reason
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
        quantity_reason = _vape_quantity_reject_reason(product)
        if quantity_reason:
            return quantity_reason
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
        "quality": quality,
        "last_success": row.get("collected_at"),
        "freshness": row.get("freshness"),
        "errors": row.get("errors", []),
    }


def merge_shards(shards: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for shard in shards:
        clean, denied = sanitize(list(shard.get("products") or []))
        accepted.extend(clean)
        rejected.extend(denied)
        sources.append(_source_status(shard, len(clean), len(denied)))
    products = dedupe(accepted)
    rejection_counts = Counter(str(row.get("reason") or "unknown") for row in rejected)
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "generated_at": now(),
        "products": products,
        "product_count": len(products),
        "rejected_products": len(rejected),
        "rejection_counts": dict(sorted(rejection_counts.items())),
    }
    status = {
        "schema_version": "dropfinder-cloud-status-v4",
        "generated_at": catalog["generated_at"],
        "summary": {
            "configured_sources": len(sources),
            "active_sources": sum(1 for row in sources if row["products"] > 0),
            "products": len(products),
            "rejected_products": len(rejected),
            "degraded_sources": sum(1 for row in sources if row["products"] == 0),
        },
        "sources": sources,
        "rejections": rejected,
    }
    return catalog, status


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge DropFinder multi-product worker shards")
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    catalog, status = merge_shards(load_shards(args.shards))
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.catalog.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.status.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(status["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
