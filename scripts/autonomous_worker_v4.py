#!/usr/bin/env python3
"""Stable production wrapper for generalized autonomous DropFinder workers."""
from __future__ import annotations

import json
import socket
import sys
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Keep the proven reliability and retry layer. Multi-product support patches its
# classification, normalization, route registry, and admission seams only.
import autonomous_worker_v2 as reliability  # type: ignore
from multi_product import publication
from multi_product.runtime import install_multi_product_runtime, runtime_self_test
from vendor_expansion import apply_registry, load_registry

worker = reliability.worker

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry remains bounded.
reliability.RETRYABLE_HTTP.add(403)

# Preserve scanner-classified transport failures before applying the existing
# HTTP status policy. The v2 retry loop resolves this symbol at runtime.
_http_route_is_retryable = reliability._route_is_retryable


def _structured_route_is_retryable(route: dict) -> bool:
    if route.get("retryable") is True:
        return True
    return _http_route_is_retryable(route)


reliability._route_is_retryable = _structured_route_is_retryable

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")

# Install the vetted vendor registry before the generalized runtime augments
# existing sources with its wider store routes.
VENDOR_EXPANSION = load_registry()
INSTALLED_VENDOR_IDS = apply_registry(worker, VENDOR_EXPANSION)


def install_runtime() -> dict:
    """Install generalized classification and the listing-card provenance gate."""
    state = install_multi_product_runtime(reliability)
    if getattr(worker, "_listing_card_provenance_gate_installed", False):
        return state
    original_gate = worker.gate

    def provenance_gate(products: list[dict]) -> tuple[bool, list[str], dict]:
        _, reasons, quality = original_gate(products)
        reasons = list(reasons)
        quality = dict(quality)
        unverified_cards = sum(
            isinstance(row.get("classification_evidence"), dict)
            and row["classification_evidence"].get("evidence_source") == "product_card_title_or_url"
            for row in products
        )
        if unverified_cards:
            reasons.append("unverified_listing_card_evidence")
            quality["unverified_listing_cards"] = unverified_cards
        return not reasons, reasons, quality

    worker.gate = provenance_gate
    worker._listing_card_provenance_gate_installed = True
    return state


def self_test() -> int:
    # Validate the pre-existing reliability layer, the generalized runtime, and
    # the independently validated vendor registry as one production composition.
    reliability.self_test()
    state = install_runtime()
    runtime_self_test(reliability)

    classify = worker.aggregate.classify_route_failure
    assert classify(TimeoutError("timed out")) == {
        "error_category": "transport_timeout",
        "retryable": True,
    }
    assert classify(ConnectionResetError("reset"))["retryable"] is True
    assert classify(ValueError("invalid JSON")) == {
        "error_category": "processing_error",
        "retryable": False,
    }
    temporary_dns_code = getattr(socket, "EAI_AGAIN", None)
    if temporary_dns_code is not None:
        temporary_dns = urllib.error.URLError(
            socket.gaierror(temporary_dns_code, "temporary failure")
        )
        assert classify(temporary_dns) == {
            "error_category": "temporary_dns_failure",
            "retryable": True,
        }
    assert reliability._route_is_retryable({"retryable": True})
    assert not reliability._route_is_retryable({"retryable": False})

    original_fetch = worker.core.fetch
    timeout_route = ("html", "https://example.test/timeout", "thca_flower")

    def timeout_fetch(_target: str):
        raise TimeoutError("timed out")

    worker.core.fetch = timeout_fetch
    try:
        timeout_products, timeout_status = reliability._original_scan_all_routes(
            ("timeout_fixture", "Timeout Fixture", [timeout_route])
        )
    finally:
        worker.core.fetch = original_fetch
    assert timeout_products == []
    timeout_result = timeout_status["route_results"][0]
    assert timeout_result["error_category"] == "transport_timeout"
    assert timeout_result["retryable"] is True
    assert reliability._is_retryable(timeout_status)

    responses = {
        "https://example.test/products/stale-thca-flower": (
            '<meta property="og:title" content="Ceramic Coffee Mug">',
            "text/html",
            200,
        ),
        "https://example.test/products/verified": (
            """
            <meta property="og:title" content="Verified THCA Flower">
            <meta name="description" content="Loose indoor THCA flower buds">
            <meta property="product:price:amount" content="31.00">
            <meta property="product:availability" content="in stock">
            """,
            "text/html",
            200,
        ),
    }

    def fake_fetch(target: str) -> tuple[str, str, int]:
        return responses[target]

    def candidate(slug: str) -> dict:
        return {
            "name": "Listing Claims THCA Flower",
            "url": f"https://example.test/products/{slug}",
            "price": 24.99,
            "stock": "in_stock",
            "card_evidence": f"Listing Claims THCA Flower /products/{slug}",
        }

    worker.core.fetch = fake_fetch
    try:
        assert reliability.descriptive_candidate_to_row(
            candidate("stale-thca-flower"), "fixture", "Fixture"
        ) is None
        verified = reliability.descriptive_candidate_to_row(
            candidate("verified"), "fixture", "Fixture"
        )
        assert verified is not None
        assert verified["primary_type"] == "cannabis_flower"
        assert verified["classification_evidence"]["evidence_source"] == "product_detail_metadata"
        assert worker.gate([verified])[0]
        assert publication.reject_reason(verified) is None

        card_derived = dict(verified)
        card_derived["classification_evidence"] = {
            **verified["classification_evidence"],
            "evidence_source": "product_card_title_or_url",
        }
        admitted, reasons, quality = worker.gate([card_derived])
        assert admitted is False
        assert "unverified_listing_card_evidence" in reasons
        assert quality["unverified_listing_cards"] == 1
    finally:
        worker.core.fetch = original_fetch

    structured_route = (
        "shopify",
        "https://example.test/collections/thca-flower/products.json?limit=250",
        "thca_flower",
    )
    structured_payload = json.dumps(
        {
            "products": [
                {
                    "title": "Blue Dream THCA Flower",
                    "handle": "blue-dream",
                    "body_html": "Loose indoor THCA flower buds 3.5g",
                    "variants": [
                        {
                            "id": 101,
                            "title": "3.5g",
                            "price": "35.00",
                            "available": True,
                        }
                    ],
                }
            ]
        }
    )
    structured = worker.core.shopify(
        structured_payload, "fixture", "Fixture", structured_route
    )
    structured = worker.verify_products(structured, "fixture", "Fixture")
    assert len(structured) == 1
    assert structured[0]["classification_evidence"]["evidence_source"] == "storefront_record"
    assert worker.gate(structured)[0]
    assert publication.reject_reason(structured[0]) is None

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
    install_runtime()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
