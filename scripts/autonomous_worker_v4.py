#!/usr/bin/env python3
"""Stable production wrapper for generalized autonomous DropFinder workers."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Keep the proven reliability and retry layer. Multi-product support patches its
# classification, normalization, route registry, and admission seams only.
import autonomous_worker_v2 as reliability  # type: ignore
from multi_product.runtime import install_multi_product_runtime, runtime_self_test
from vendor_expansion import apply_registry, load_registry

worker = reliability.worker
UNVERIFIED_CARD_EVIDENCE = "product_card_title_or_url"

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry remains bounded.
reliability.RETRYABLE_HTTP.add(403)

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")

# Install the vetted vendor registry before the generalized runtime augments
# existing sources with its wider store routes.
VENDOR_EXPANSION = load_registry()
INSTALLED_VENDOR_IDS = apply_registry(worker, VENDOR_EXPANSION)


def _install_runtime() -> dict[str, Any]:
    state = install_multi_product_runtime(reliability)
    if getattr(worker, "_listing_card_authority_gate_installed", False):
        return state

    original_gate = worker.gate

    def authority_gate(products: list[dict[str, Any]]) -> tuple[bool, list[str], dict[str, Any]]:
        admitted, reasons, quality = original_gate(products)
        unverified = sum(
            isinstance(row.get("classification_evidence"), dict)
            and row["classification_evidence"].get("evidence_source") == UNVERIFIED_CARD_EVIDENCE
            for row in products
        )
        quality = dict(quality)
        quality["unverified_listing_card_products"] = unverified
        if unverified:
            reasons = sorted(set([*reasons, "unverified_listing_card_evidence"]))
            admitted = False
        return admitted, reasons, quality

    worker.gate = authority_gate
    worker._listing_card_authority_gate_installed = True
    return state


def self_test() -> int:
    # Validate the pre-existing reliability layer, the generalized runtime, and
    # the independently validated vendor registry as one production composition.
    reliability.self_test()
    state = _install_runtime()
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

    row = worker.core.record(
        "fixture",
        "Fixture",
        ("html", "https://example.test/shop", "storewide"),
        "Blue Dream THCA Flower 3.5g",
        "https://example.test/products/blue-dream",
        "Loose indoor THCA flower buds",
        25,
        "in_stock",
    )
    assert row is not None
    unverified = dict(row)
    unverified["classification_evidence"] = dict(row["classification_evidence"])
    unverified["classification_evidence"]["evidence_source"] = UNVERIFIED_CARD_EVIDENCE
    admitted, reasons, quality = worker.gate([unverified])
    assert not admitted
    assert "unverified_listing_card_evidence" in reasons
    assert quality["unverified_listing_card_products"] == 1
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    _install_runtime()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
