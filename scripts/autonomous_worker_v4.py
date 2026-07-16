#!/usr/bin/env python3
"""Stable production wrapper for generalized autonomous DropFinder workers."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Keep the proven reliability and retry layer. Multi-product support patches its
# classification, normalization, route registry, and admission seams only.
import autonomous_worker_v2 as reliability  # type: ignore
from multi_product.runtime import install_multi_product_runtime, runtime_self_test

worker = reliability.worker

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry remains bounded.
reliability.RETRYABLE_HTTP.add(403)

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")


def self_test() -> int:
    # Validate the pre-existing strict worker first, before installing the wider
    # type-aware policy. This catches regressions in the transport/retry layer.
    reliability.self_test()
    state = install_multi_product_runtime(reliability)
    runtime_self_test(reliability)
    assert state["installed"] is True
    assert state["source_count"] >= 18
    assert 403 in reliability.RETRYABLE_HTTP
    assert "/cbd-hemp-flower/" in worker.PRODUCT_PATHS
    assert "green_unicorn_farms" in worker.FALLBACK_HTML_ROUTES
    assert "cali_canna" in worker.FALLBACK_HTML_ROUTES
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    install_multi_product_runtime(reliability)
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
