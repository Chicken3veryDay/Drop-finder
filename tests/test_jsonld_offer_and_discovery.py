from __future__ import annotations

import json
import unittest

from scripts import cloud_scan
from scripts.catalog_v4 import build_catalog


ROUTE = ("html", "https://example.test/collections/thca-flower", "thca_flower")


def product_jsonld(offers: list[dict], *, name: str = "Blue Dream THCA Flower") -> str:
    return "<script type='application/ld+json'>" + json.dumps({
        "@type": "Product",
        "@id": "blue-dream",
        "sku": "blue-dream",
        "name": name,
        "description": "Loose THCA flower",
        "url": "https://example.test/products/blue-dream",
        "offers": offers,
    }) + "</script>"


def offer(label: str, variant: str, price: str, availability: str = "https://schema.org/InStock") -> dict:
    return {
        "@type": "Offer",
        "name": label,
        "sku": variant,
        "url": f"https://example.test/products/blue-dream?variant={variant}",
        "price": price,
        "availability": availability,
    }


class JsonLdOfferAndDiscoveryTests(unittest.TestCase):
    def test_every_explicit_in_stock_package_offer_is_preserved(self) -> None:
        payload = product_jsonld([
            offer("3.5g", "35", "25.00"),
            offer("7g", "70", "45.00"),
            offer("14g", "140", "80.00", "https://schema.org/OutOfStock"),
        ])
        rows = cloud_scan.html_products(payload, "fixture", "Fixture Vendor", ROUTE)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["grams"] for row in rows], [3.5, 7.0])
        self.assertEqual([row["price"] for row in rows], [25.0, 45.0])
        self.assertEqual([row["source_variant_id"] for row in rows], ["35", "70"])
        self.assertEqual(
            [row["url"] for row in rows],
            [
                "https://example.test/products/blue-dream?variant=35",
                "https://example.test/products/blue-dream?variant=70",
            ],
        )
        result = build_catalog(rows, generated_at="2026-07-19T12:00:00Z", detail_shards=1)
        self.assertEqual(result.product_count, 1)
        self.assertEqual(result.variant_count, 2)

    def test_same_weight_seller_alternatives_follow_deterministic_identity_policy(self) -> None:
        payload = product_jsonld([
            offer("3.5g", "seller-z", "24.00"),
            offer("3.5g", "seller-a", "25.00"),
        ])
        rows = cloud_scan.html_products(payload, "fixture", "Fixture Vendor", ROUTE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_variant_id"], "seller-a")
        self.assertEqual(rows[0]["price"], 25.0)

    def test_single_offer_without_package_identity_remains_one_product_row(self) -> None:
        payload = product_jsonld([{
            "@type": "Offer",
            "url": "https://example.test/products/blue-dream",
            "price": "25.00",
            "availability": "https://schema.org/InStock",
        }], name="Blue Dream THCA Flower 3.5g")
        rows = cloud_scan.html_products(payload, "fixture", "Fixture Vendor", ROUTE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["grams"], 3.5)

    def test_partial_jsonld_does_not_suppress_uncovered_product_links(self) -> None:
        payload = product_jsonld([offer("3.5g", "35", "25.00")]) + """
        <a href='/products/blue-dream'>Blue Dream THCA Flower</a>
        <a href='/products/gelato-thca-flower'>Gelato THCA Flower</a>
        <a href='/products/runtz-thca-flower'>Runtz THCA Flower</a>
        """
        responses = {
            "https://example.test/products/gelato-thca-flower": (
                "<meta property='og:title' content='Gelato THCA Flower 3.5g'>"
                "<meta property='og:description' content='Loose THCA flower 3.5g'>"
                "<meta property='product:price:amount' content='30'>"
                "<meta property='product:availability' content='in stock'>",
                "text/html",
                200,
            ),
            "https://example.test/products/runtz-thca-flower": (
                "<meta property='og:title' content='Runtz THCA Flower 7g'>"
                "<meta property='og:description' content='Loose THCA flower 7g'>"
                "<meta property='product:price:amount' content='50'>"
                "<meta property='product:availability' content='in stock'>",
                "text/html",
                200,
            ),
        }
        calls: list[str] = []
        original = cloud_scan.fetch
        cloud_scan.fetch = lambda target: (calls.append(target) or responses[target])
        diagnostics: dict = {}
        try:
            rows = cloud_scan.html_with_details(payload, "fixture", "Fixture Vendor", ROUTE, diagnostics)
        finally:
            cloud_scan.fetch = original
        self.assertEqual(len(rows), 3)
        self.assertEqual(calls, list(responses))
        self.assertEqual(diagnostics["structured_rows"], 1)
        self.assertEqual(diagnostics["discovered_links"], 3)
        self.assertEqual(diagnostics["uncovered_links"], 2)
        self.assertEqual(diagnostics["detail_requests"], 2)
        self.assertEqual(diagnostics["detail_failures"], 0)
        self.assertEqual(diagnostics["coverage_status"], "complete")

    def test_uncovered_detail_failure_is_observable_and_survivors_remain(self) -> None:
        payload = product_jsonld([offer("3.5g", "35", "25.00")]) + """
        <a href='/products/blue-dream'>Blue Dream THCA Flower</a>
        <a href='/products/missing-thca-flower'>Missing THCA Flower</a>
        """
        original = cloud_scan.fetch
        cloud_scan.fetch = lambda _target: (_ for _ in ()).throw(TimeoutError("timeout"))
        diagnostics: dict = {}
        try:
            rows = cloud_scan.html_with_details(payload, "fixture", "Fixture Vendor", ROUTE, diagnostics)
        finally:
            cloud_scan.fetch = original
        self.assertEqual(len(rows), 1)
        self.assertEqual(diagnostics["detail_failures"], 1)
        self.assertEqual(diagnostics["detail_failure_reasons"], {"timeout_error": 1})
        self.assertEqual(diagnostics["coverage_status"], "partial")


if __name__ == "__main__":
    unittest.main()
