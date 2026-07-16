#!/usr/bin/env python3
"""Stable production wrapper for strict autonomous DropFinder workers."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Import the proven reliability layer directly. The experimental global
# browser-transport wrapper is intentionally not imported because it reduced
# successful source coverage on live GitHub-hosted runs.
import autonomous_worker_v2 as reliability  # type: ignore
import multi_product  # type: ignore

worker = reliability.worker

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry is bounded and does not turn a
# persistent block into a fake success.
reliability.RETRYABLE_HTTP.add(403)

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
# Product-detail evidence remains mandatory after candidate discovery.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")

# Install the narrow type-aware classifier after the reliability layer has
# finished wiring its candidate scoring and retry wrappers.
multi_product.install(reliability)

# Older worker fixtures predate the top-level product_type field and retain the
# same classification inside classification_evidence. Normalize that legacy
# shape before the stricter typed gate runs. Live records already carry both.
_type_aware_gate = worker.gate


def compatible_gate(products: list[dict]) -> tuple[bool, list[str], dict]:
    normalized: list[dict] = []
    for product in products:
        row = dict(product)
        evidence = row.get("classification_evidence")
        if not row.get("product_type") and isinstance(evidence, dict):
            evidence_type = evidence.get("product_type")
            if isinstance(evidence_type, str) and evidence_type:
                row["product_type"] = evidence_type
        normalized.append(row)
    return _type_aware_gate(normalized)


worker.gate = compatible_gate


def self_test() -> int:
    reliability.self_test()
    multi_product.self_test()
    assert 403 in reliability.RETRYABLE_HTTP
    assert "/cbd-hemp-flower/" in worker.PRODUCT_PATHS
    assert "green_unicorn_farms" in worker.FALLBACK_HTML_ROUTES
    assert worker.has_product_evidence("THCA disposable vape 1g")
    assert worker.has_product_evidence("Amanita mushroom caps 7g")
    assert not worker.has_product_evidence("Nicotine disposable vape")
    assert any(
        route[2] == "storewide"
        for source_id, _vendor, routes in worker.core.SOURCES
        if source_id == "sherlocks_glass"
        for route in routes
    )
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
