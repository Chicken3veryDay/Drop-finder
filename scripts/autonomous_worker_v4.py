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
import fallback_transport  # type: ignore
from multi_product.runtime import install_multi_product_runtime, runtime_self_test
from vendor_expansion import apply_registry, load_registry

worker = reliability.worker

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry remains bounded.
reliability.RETRYABLE_HTTP.add(403)

# Apply the same bounded status/content-type transport contract to fallback
# category roots before any product-card parsing can occur.
fallback_transport.install(reliability)

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")

# Install the vetted vendor registry before the generalized runtime augments
# existing sources with its wider store routes.
VENDOR_EXPANSION = load_registry()
INSTALLED_VENDOR_IDS = apply_registry(worker, VENDOR_EXPANSION)


def self_test() -> int:
    # Validate the pre-existing reliability layer, fallback transport boundary,
    # generalized runtime, and independently validated vendor registry together.
    reliability.self_test()
    fallback_transport.self_test(reliability)
    state = install_multi_product_runtime(reliability)
    runtime_self_test(reliability)
    vendors = VENDOR_EXPANSION["vendors"]
    source_ids = {source[0] for source in worker.core.SOURCES}

    assert state["installed"] is True
    assert state["source_count"] >= 38
    assert 403 in reliability.RETRYABLE_HTTP
    assert "/cbd-hemp-flower/" in worker.PRODUCT_PATHS
    assert "green_unicorn_farms" in worker.FALLBACK_HTML_ROUTES
    assert len(vendors) >= 20
    assert len({vendor["vendor_id"] for vendor in vendors}) == len(vendors)
    for required in ("cali_canna", "flow_gardens", "dr_ganja", "the_hemp_collect", "eight_horses_hemp"):
        assert required in source_ids
        assert required in worker.FALLBACK_HTML_ROUTES
    assert set(INSTALLED_VENDOR_IDS).issubset(source_ids)
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    install_multi_product_runtime(reliability)
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
