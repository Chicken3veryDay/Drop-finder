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
