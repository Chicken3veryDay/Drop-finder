from __future__ import annotations

import json
import unittest

from scripts import cloud_scan
from scripts.catalog_v4 import build_catalog


class JsonLdOfferAndDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_fetch = cloud_scan.fetch
        self.route = (
            "html",
            "https://example.test/collections/thca-flower",
            "thca_flower",
        )

    def tearDown(self) -> None:
        cloud_scan.fetch = self.original_fetch

    @staticmethod
    def page(product: dict, links: list[tuple[str, str]] | None = None) -> str:
        anchors = "\n".join(
            f'<a href="{href}">{label}</a>' for href, label in (links or [])
        )
        return (
            '<script type="application/ld+json">'
            + json.dumps(product)
            + "</script>\n"
            + anchors
        )

    @staticmethod
    def detail(name: str, price: str = "30.00", stock: str = "instock") -> str:
        return f"""
        <html>
          <head>
            <meta property="og:title" content="{name}">
            <meta property="og:description" content="Indoor loose THCA flower 3.5g">
            <meta property="product:price:amount" content="{price}">
            <meta property="product:availability" content="{stock}">
          </head>
        </html>
        """

    @staticmethod
    def product(offers: list[dict] | dict | None) -> dict:
        product = {
            "@type": "Product",
            "productID": "blue-dream",
            "name": "Blue Dream THCA Flower",
            "description": "Indoor loose THCA flower",
            "url": "https://example.test/products/blue-dream",
            "image": "https://example.test/media/blue.jpg",
        }
        if offers is not None:
            product["offers"] = offers
        return product

    @staticmethod
    def offer(
        label: str,
        variant_id: str,
        price: str,
        *,
        stock: str = "https://schema.org/InStock",
        host: str = "example.test",
    ) -> dict:
        return {
            "@type": "Offer",
            "name": label,
            "sku": variant_id,
            "url": f"https://{host}/products/blue-dream?variant={variant_id}",
            "price": price,
            "availability": stock,
        }

    def test_weighted_offer_array_emits_every_in_stock_package(self) -> None:
        payload = self.page(
            self.product(
                [
                    self.offer("3.5g", "35", "25.00"),
                    self.offer("7g", "70", "45.00"),
                ]
            )
        )
        rows = cloud_scan.html_products(payload, "fixture", "Fixture", self.route)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["grams"] for row in rows}, {3.5, 7.0})
        self.assertEqual({row["price"] for row in rows}, {25.0, 45.0})
        self.assertEqual({row["variant"] for row in rows}, {"3.5g", "7g"})
        self.assertEqual({row["source_variant_id"] for row in rows}, {"35", "70"})
        self.assertTrue(all("variant=" in row["url"] for row in rows))

        result = build_catalog(
            rows,
            generated_at="2026-07-19T00:00:00Z",
            detail_shards=1,
        )
        self.assertEqual(result.manifest["product_count"], 1)
        self.assertEqual(result.manifest["in_stock_variant_count"], 2)

    def test_out_of_stock_offer_is_not_published(self) -> None:
        payload = self.page(
            self.product(
                [
                    self.offer("3.5g", "35", "25.00"),
                    self.offer(
                        "7g",
                        "70",
                        "45.00",
                        stock="https://schema.org/OutOfStock",
                    ),
                ]
            )
        )
        rows = cloud_scan.html_products(payload, "fixture", "Fixture", self.route)
        self.assertEqual([row["source_variant_id"] for row in rows], ["35"])

    def test_same_weight_seller_alternatives_prefer_product_owned_offer(self) -> None:
        payload = self.page(
            self.product(
                [
                    self.offer("3.5g", "seller", "20.00", host="market.example"),
                    self.offer("3.5g", "owned", "25.00"),
                ]
            )
        )
        rows = cloud_scan.html_products(payload, "fixture", "Fixture", self.route)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_variant_id"], "owned")
        self.assertEqual(rows[0]["price"], 25.0)
        self.assertEqual(rows[0]["url"], "https://example.test/products/blue-dream?variant=owned")

    def test_ambiguous_multi_seller_offers_do_not_invent_package_variants(self) -> None:
        payload = self.page(
            self.product(
                [
                    {
                        "@type": "Offer",
                        "name": "Seller A",
                        "url": "https://seller-a.example/blue-dream",
                        "price": "24.00",
                        "availability": "https://schema.org/InStock",
                    },
                    {
                        "@type": "Offer",
                        "name": "Seller B",
                        "url": "https://seller-b.example/blue-dream",
                        "price": "23.00",
                        "availability": "https://schema.org/InStock",
                    },
                ]
            )
        )
        self.assertEqual(
            cloud_scan.html_products(payload, "fixture", "Fixture", self.route),
            [],
        )

    def test_partial_structured_results_fetch_only_uncovered_links(self) -> None:
        payload = self.page(
            self.product(self.offer("3.5g", "35", "25.00")),
            [
                ("/products/blue-dream", "Blue Dream THCA Flower"),
                ("/products/gelato-thca-flower", "Gelato THCA Flower"),
                ("/products/runtz-thca-flower", "Runtz THCA Flower"),
            ],
        )
        calls: list[str] = []

        def fetch(target: str):
            calls.append(target)
            if target.endswith("/gelato-thca-flower"):
                return self.detail("Gelato THCA Flower 3.5g", "30.00"), "text/html", 200
            if target.endswith("/runtz-thca-flower"):
                return self.detail("Runtz THCA Flower 3.5g", "32.00"), "text/html", 200
            raise AssertionError(f"covered structured product was fetched: {target}")

        cloud_scan.fetch = fetch
        diagnostics: dict = {}
        rows = cloud_scan.html_with_details(
            payload,
            "fixture",
            "Fixture",
            self.route,
            diagnostics,
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(diagnostics["structured_products"], 1)
        self.assertEqual(diagnostics["discovered_product_links"], 3)
        self.assertEqual(diagnostics["covered_product_links"], 1)
        self.assertEqual(diagnostics["detail_requests"], 2)
        self.assertEqual(diagnostics["detail_failures"], 0)
        self.assertEqual(
            {row["name"] for row in rows},
            {
                "Blue Dream THCA Flower 3.5g",
                "Gelato THCA Flower 3.5g",
                "Runtz THCA Flower 3.5g",
            },
        )

    def test_detail_failure_preserves_survivors_and_marks_source_degraded(self) -> None:
        payload = self.page(
            self.product(self.offer("3.5g", "35", "25.00")),
            [
                ("/products/blue-dream", "Blue Dream THCA Flower"),
                ("/products/gelato-thca-flower", "Gelato THCA Flower"),
                ("/products/runtz-thca-flower", "Runtz THCA Flower"),
            ],
        )

        def fetch(target: str):
            if target == self.route[1]:
                return payload, "text/html", 200
            if target.endswith("/gelato-thca-flower"):
                return self.detail("Gelato THCA Flower 3.5g"), "text/html", 200
            if target.endswith("/runtz-thca-flower"):
                raise TimeoutError("detail timed out")
            raise AssertionError(target)

        cloud_scan.fetch = fetch
        rows, status = cloud_scan.scan(("fixture", "Fixture", [self.route]))

        self.assertEqual(len(rows), 2)
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(status["health_reason_codes"], ["html_detail_discovery_incomplete"])
        route_status = status["route_results"][0]
        self.assertEqual(route_status["detail_failures"], 1)
        self.assertEqual(route_status["detail_failure_reasons"], {"detail_timeouterror": 1})

    def test_single_structured_product_does_not_trigger_redundant_fetch(self) -> None:
        payload = self.page(
            self.product(self.offer("3.5g", "35", "25.00")),
            [("/products/blue-dream", "Blue Dream THCA Flower")],
        )
        calls = 0

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            raise AssertionError("covered product must not be fetched")

        cloud_scan.fetch = fetch
        diagnostics: dict = {}
        rows = cloud_scan.html_with_details(
            payload,
            "fixture",
            "Fixture",
            self.route,
            diagnostics,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(calls, 0)
        self.assertEqual(diagnostics["covered_product_links"], 1)
        self.assertEqual(diagnostics["detail_requests"], 0)


if __name__ == "__main__":
    unittest.main()
