#!/usr/bin/env python3
"""Probe public storefront APIs for variant and attribute structures without storing raw payloads."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cloud_scan

UA = "DropFinder-Commerce-Schema-Probe/1.1"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str) -> tuple[Any | None, int, str | None]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response), int(getattr(response, "status", 200)), None
    except urllib.error.HTTPError as exc:
        return None, int(exc.code), f"HTTP {exc.code}"
    except Exception as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"[:400]


def shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            return sorted(value.keys())[:80]
        return type(value).__name__
    if isinstance(value, dict):
        return {str(key): shape(item, depth + 1) for key, item in list(value.items())[:80]}
    if isinstance(value, list):
        return [shape(item, depth + 1) for item in value[:3]]
    if isinstance(value, str):
        return value[:160]
    return value


def variation_ids(product: dict[str, Any]) -> list[int]:
    result: list[int] = []
    for row in product.get("variations") or []:
        if not isinstance(row, dict):
            continue
        try:
            value = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            result.append(value)
    return result


def probe_woo(source_id: str, vendor: str, route: tuple) -> dict[str, Any]:
    payload, status, error = fetch_json(route[1])
    result: dict[str, Any] = {
        "source_id": source_id,
        "vendor": vendor,
        "route": route[1],
        "route_status": status,
        "error": error,
    }
    products = payload if isinstance(payload, list) else payload.get("products", []) if isinstance(payload, dict) else []
    result["returned_products"] = len(products)
    candidates = [
        row for row in products
        if isinstance(row, dict)
        and (row.get("has_options") or row.get("variations") or len(row.get("attributes") or []) > 0)
    ]
    product = candidates[0] if candidates else next((row for row in products if isinstance(row, dict)), None)
    if not product:
        return result
    product_id = product.get("id")
    result["sample_product"] = {
        "id": product_id,
        "name": product.get("name"),
        "has_options": product.get("has_options"),
        "is_purchasable": product.get("is_purchasable"),
        "is_in_stock": product.get("is_in_stock"),
        "prices": shape(product.get("prices")),
        "attributes": shape(product.get("attributes")),
        "variations": shape(product.get("variations")),
        "add_to_cart": shape(product.get("add_to_cart")),
        "top_level_keys": sorted(product.keys()),
    }
    if product_id:
        root = route[1].split("/products?", 1)[0].rstrip("/")
        for label, url in (
            ("product_detail", f"{root}/products/{product_id}"),
            ("variations", f"{root}/products/{product_id}/variations"),
        ):
            detail, detail_status, detail_error = fetch_json(url)
            result[label] = {
                "url": url,
                "status": detail_status,
                "error": detail_error,
                "shape": shape(detail),
            }
        detail_rows = []
        for variation_id in variation_ids(product)[:4]:
            url = f"{root}/products/{variation_id}"
            detail, detail_status, detail_error = fetch_json(url)
            detail_rows.append({
                "variation_id": variation_id,
                "url": url,
                "status": detail_status,
                "error": detail_error,
                "shape": shape(detail),
            })
        result["variation_details"] = detail_rows
    return result


def probe_shopify(source_id: str, vendor: str, route: tuple) -> dict[str, Any]:
    payload, status, error = fetch_json(route[1])
    products = payload.get("products", []) if isinstance(payload, dict) else []
    product = next((row for row in products if isinstance(row, dict) and len(row.get("variants") or []) > 1), None)
    product = product or next((row for row in products if isinstance(row, dict)), None)
    return {
        "source_id": source_id,
        "vendor": vendor,
        "route": route[1],
        "route_status": status,
        "error": error,
        "returned_products": len(products),
        "sample_product": None if not product else {
            "id": product.get("id"),
            "title": product.get("title"),
            "options": shape(product.get("options")),
            "variants": shape(product.get("variants")),
            "top_level_keys": sorted(product.keys()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("deployment/commerce-schema-probe.json"))
    args = parser.parse_args()
    results = []
    for source_id, vendor, routes in cloud_scan.SOURCES:
        for route in routes:
            if route[0] == "woo":
                results.append(probe_woo(source_id, vendor, route))
                break
            if route[0] == "shopify":
                results.append(probe_shopify(source_id, vendor, route))
                break
    report = {
        "schema_version": "dropfinder-commerce-schema-probe-v2",
        "probed_at": now(),
        "sources": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
