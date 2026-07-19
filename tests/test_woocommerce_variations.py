from __future__ import annotations

import json
import urllib.error
import urllib.parse
import unittest

from scripts import cloud_scan
from scripts.catalog_v4 import build_catalog


class WooCommerceVariationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_fetch = cloud_scan.fetch
        self.original_delays = cloud_scan.WOO_VARIATION_RETRY_DELAYS
        cloud_scan.WOO_VARIATION_RETRY_DELAYS = (0.0, 0.0, 0.0)
        self.route = (
            "woo",
            "https://shop.example/wp-json/wc/store/v1/products?per_page=100&search=flower",
            "mixed_flower",
        )

    def tearDown(self) -> None:
        cloud_scan.fetch = self.original_fetch
        cloud_scan.WOO_VARIATION_RETRY_DELAYS = self.original_delays

    def parent(self, *, variable: bool = True) -> dict:
        return {
            "id": 42,
            "name": "Blue Lobster Premium THCA Flower",
            "permalink": "https://shop.example/product/blue-lobster/",
            "has_options": variable,
            "type": "variable" if variable else "simple",
            "short_description": "Indoor THCA flower",
            "description": "Premium loose flower buds",
            "categories": [{"name": "THCA Flower"}],
            "prices": {
                "currency_minor_unit": 2,
                "price": "2500",
                "regular_price": "3000",
                "price_range": {"min_amount": "2500", "max_amount": "9000"},
            },
            "stock_status": "instock",
            "images": [{"src": "https://shop.example/media/blue.jpg"}],
        }

    def variation(self, variation_id: int, label: str, price: int, stock: str = "instock") -> dict:
        return {
            "id": variation_id,
            "parent": 42,
            "type": "variation",
            "name": f"Blue Lobster Premium THCA Flower - {label}",
            "variation": label,
            "permalink": f"https://shop.example/product/blue-lobster/?attribute_weight={urllib.parse.quote(label)}",
            "prices": {
                "currency_minor_unit": 2,
                "price": str(price),
                "regular_price": str(price + 500),
            },
            "stock_status": stock,
            "is_in_stock": stock == "instock",
            "images": [{"src": "https://shop.example/media/blue.jpg"}],
            "attributes": [{"name": "Weight", "value": label}],
        }

    def variable_payload(self) -> str:
        return json.dumps([self.parent()])

    def test_variable_parent_emits_one_row_per_in_stock_package(self) -> None:
        variations = [
            self.variation(101, "3.5g", 2500),
            self.variation(102, "7g", 4500),
            self.variation(103, "14g", 7000),
            self.variation(104, "28g", 9000),
        ]
        calls: list[str] = []

        def fetch(target: str):
            calls.append(target)
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(target).query)
            self.assertEqual(query["type"], ["variation"])
            self.assertEqual(query["parent"], ["42"])
            self.assertEqual(query["page"], ["1"])
            return json.dumps(variations), "application/json", 200

        cloud_scan.fetch = fetch
        rows, diagnostics = cloud_scan.woo(self.variable_payload(), "fixture", "Fixture", self.route)

        self.assertEqual(len(rows), 4)
        self.assertEqual({row["source_product_id"] for row in rows}, {"42"})
        self.assertEqual({row["source_variant_id"] for row in rows}, {"101", "102", "103", "104"})
        self.assertEqual({row["variant"] for row in rows}, {"3.5g", "7g", "14g", "28g"})
        self.assertEqual({row["grams"] for row in rows}, {3.5, 7.0, 14.0, 28.0})
        self.assertEqual({row["price"] for row in rows}, {25.0, 45.0, 70.0, 90.0})
        self.assertTrue(all("variant=" in row["url"] for row in rows))
        self.assertEqual(diagnostics["variable_parents"], 1)
        self.assertEqual(diagnostics["variation_failures"], 0)
        self.assertEqual(len(calls), 1)

    def test_sold_out_and_unknown_variations_do_not_enter_catalog(self) -> None:
        variations = [
            self.variation(101, "3.5g", 2500, "instock"),
            self.variation(102, "7g", 4500, "outofstock"),
            self.variation(103, "14g", 7000, "unknown"),
        ]
        cloud_scan.fetch = lambda _target: (json.dumps(variations), "application/json", 200)
        rows, diagnostics = cloud_scan.woo(self.variable_payload(), "fixture", "Fixture", self.route)
        self.assertEqual([row["source_variant_id"] for row in rows], ["101"])
        self.assertEqual(diagnostics["variation_rejections"], 2)
        self.assertEqual(diagnostics["variation_rejection_reasons"], {
            "variation_not_explicitly_in_stock": 2,
        })

    def test_simple_product_emits_one_row_without_variation_request(self) -> None:
        calls = 0

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            raise AssertionError("simple products must not request variations")

        cloud_scan.fetch = fetch
        parent = self.parent(variable=False)
        parent["name"] = "Simple THCA Flower 3.5g"
        parent["short_description"] = "3.5g loose flower buds"
        rows, diagnostics = cloud_scan.woo(json.dumps([parent]), "fixture", "Fixture", self.route)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_product_id"], "42")
        self.assertEqual(rows[0]["source_variant_id"], "")
        self.assertEqual(rows[0]["price"], 25.0)
        self.assertEqual(calls, 0)
        self.assertEqual(diagnostics["variable_parents"], 0)

    def test_retryable_variation_failure_recovers_without_duplicates(self) -> None:
        calls = 0
        variations = [self.variation(101, "3.5g", 2500)]

        def fetch(target: str):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise urllib.error.HTTPError(target, 429, "rate limited", {}, None)
            return json.dumps(variations), "application/json", 200

        cloud_scan.fetch = fetch
        rows, diagnostics = cloud_scan.woo(self.variable_payload(), "fixture", "Fixture", self.route)
        self.assertEqual(len(rows), 1)
        self.assertEqual(calls, 2)
        self.assertEqual(diagnostics["variation_retries"], 1)
        self.assertEqual(diagnostics["variation_failures"], 0)

    def test_exhausted_variation_failure_never_publishes_parent_range_price(self) -> None:
        calls = 0

        def fetch(target: str):
            nonlocal calls
            calls += 1
            raise urllib.error.HTTPError(target, 503, "unavailable", {}, None)

        cloud_scan.fetch = fetch
        rows, diagnostics = cloud_scan.woo(self.variable_payload(), "fixture", "Fixture", self.route)
        self.assertEqual(rows, [])
        self.assertEqual(calls, 3)
        self.assertEqual(diagnostics["variation_failures"], 1)
        self.assertEqual(diagnostics["variation_failure_reasons"], {"variation_http_503": 1})

    def test_variation_rows_group_into_one_catalog_product(self) -> None:
        variations = [
            self.variation(101, "3.5g", 2500),
            self.variation(102, "7g", 4500),
            self.variation(103, "14g", 7000),
            self.variation(104, "28g", 9000),
        ]
        cloud_scan.fetch = lambda _target: (json.dumps(variations), "application/json", 200)
        rows, diagnostics = cloud_scan.woo(self.variable_payload(), "fixture", "Fixture", self.route)
        self.assertEqual(diagnostics["variation_failures"], 0)
        result = build_catalog(rows, generated_at="2026-07-19T00:00:00Z", detail_shards=1)
        self.assertEqual(result.manifest["product_count"], 1)
        self.assertEqual(result.manifest["in_stock_variant_count"], 4)
        self.assertEqual(result.rejections["reason_counts"].get("invalid_or_missing_weight", 0), 0)


if __name__ == "__main__":
    unittest.main()
