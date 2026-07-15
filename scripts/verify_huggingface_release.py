#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMPARISON = "exact_price_weight_ppg_thca_stock_image_v1"
NORMALIZATION = "dropfinder-product-normalization-v1"
WEIGHT = re.compile(r"\b\d+(?:\.\d+)?\s*(?:g|grams?|oz|ounces?)\b", re.I)
LABEL = re.compile(r"\b(?:weight|size|package|amount|quantity|option)\s*:", re.I)


def fetch(base: str, path: str, *, as_json: bool = True, timeout: int = 120) -> Any:
    request = urllib.request.Request(
        base.rstrip("/") + path,
        headers={"User-Agent": "DropFinder-HF-Live-Verifier/1.0", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    return json.loads(raw) if as_json else raw


def wait_ready(base: str, attempts: int = 80) -> tuple[dict, dict]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            health = fetch(base, "/health")
            ready = fetch(base, "/ready")
            if health.get("status") == "healthy" and ready.get("ready") is True:
                return health, ready
        except Exception as exc:
            last_error = exc
        time.sleep(15)
    raise RuntimeError(f"public Space did not become ready: {last_error}")


def verify(base: str) -> dict[str, Any]:
    health, ready = wait_ready(base)
    catalog = fetch(base, "/api/catalog")
    status = fetch(base, "/api/status")
    runtime = fetch(base, "/api/runtime")
    page = fetch(base, "/", as_json=False)
    service_worker = fetch(base, "/sw.js", as_json=False)
    products = catalog.get("products") or []
    failures: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for product in products:
        failed: list[str] = []
        name = str(product.get("name") or "")
        grams = product.get("grams")
        expected_label = None
        if isinstance(grams, (int, float)) and grams > 0:
            expected_label = f"{grams:.3f}".rstrip("0").rstrip(".") + " g"
        if product.get("normalization_contract") != NORMALIZATION:
            failed.append("normalization_contract")
        if product.get("comparison_contract") != COMPARISON:
            failed.append("comparison_contract")
        if product.get("comparison_complete") is not True:
            failed.append("comparison_complete")
        if product.get("display_name") != name or not name:
            failed.append("display_name")
        if not product.get("raw_name"):
            failed.append("raw_name")
        if WEIGHT.search(name):
            failed.append("weight_in_name")
        if LABEL.search(name):
            failed.append("weight_label_in_name")
        if "thca" in name.lower() or "thc-a" in name.lower():
            failed.append("thca_in_name")
        if any(token in name for token in ("|", "_", "•", "·")):
            failed.append("source_separator_in_name")
        if product.get("package_label") != expected_label:
            failed.append("package_label")
        if product.get("variant") != expected_label:
            failed.append("variant_label")
        if not isinstance(product.get("price"), (int, float)) or product["price"] <= 0:
            failed.append("price")
        if not isinstance(product.get("price_per_gram"), (int, float)) or product["price_per_gram"] <= 0:
            failed.append("price_per_gram")
        if not isinstance(product.get("thca"), (int, float)) or not 0 < product["thca"] <= 100:
            failed.append("thca")
        if failed:
            counts.update(failed)
            failures.append(
                {
                    "id": product.get("id"),
                    "source_id": product.get("source_id"),
                    "name": name,
                    "raw_name": product.get("raw_name"),
                    "failed": sorted(set(failed)),
                }
            )

    checks = {
        "health": health.get("status") == "healthy",
        "ready": ready.get("ready") is True,
        "nonempty_strict_catalog": len(products) >= 25,
        "catalog_count": catalog.get("product_count") == len(products),
        "catalog_comparison_contract": catalog.get("comparison_contract") == COMPARISON,
        "catalog_normalization_contract": catalog.get("normalization_contract") == NORMALIZATION,
        "status_normalization_contract": status.get("normalization_contract") == NORMALIZATION,
        "runtime_normalization_contract": runtime.get("normalization_contract") == NORMALIZATION,
        "final_normalizer": status.get("services", {}).get("final_normalizer") == "healthy",
        "all_product_fields": not failures,
        "one_page_result_copy": "products on this page" in page,
        "no_pagination": all(token not in page for token in ("loadMore", "pageSize", "pagination")),
        "chunked_render": "requestIdleCallback" in page and "insertAdjacentHTML" in page,
        "offscreen_containment": "content-visibility:auto" in page and "contain-intrinsic-size:" in page,
        "lazy_async_images": 'loading="lazy"' in page and 'decoding="async"' in page and 'fetchpriority="low"' in page,
        "debounced_search": "setTimeout(render,75)" in page,
        "fast_service_worker": "dropfinder-cloud-v6" in service_worker and "event.waitUntil(refresh.catch" in service_worker,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "dropfinder-huggingface-deployment-v1",
        "status": "healthy" if not failed_checks else "invalid",
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "huggingface_space",
        "service_url": base.rstrip("/"),
        "product_count": len(products),
        "source_count": status.get("healthy_sources"),
        "comparison_contract": catalog.get("comparison_contract"),
        "normalization_contract": catalog.get("normalization_contract"),
        "field_failure_count": len(failures),
        "field_failure_counts": dict(sorted(counts.items())),
        "field_failure_examples": failures[:100],
        "checks": checks,
        "failed_checks": failed_checks,
        "sample_names": [
            {
                "source_id": row.get("source_id"),
                "raw_name": row.get("raw_name"),
                "display_name": row.get("display_name"),
                "package_label": row.get("package_label"),
            }
            for row in products[:80]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
