from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from urllib.parse import urlsplit

from scripts import cloud_scan
from scripts.catalog_v4 import build_catalog
from scripts.multi_product.runtime import install_multi_product_runtime


HTML_ROUTE = ("html", "https://example.test/collections/thca-flower", "thca_flower")
SHOPIFY_ROUTE = ("shopify", "https://example.test/collections/thca-flower/products.json?limit=250", "thca_flower")
WOO_ROUTE = ("woo", "https://example.test/wp-json/wc/store/v1/products?per_page=100", "storewide")


class CatalogMetadataExtractionTests(unittest.TestCase):
    def test_record_retains_bounded_description_and_parses_common_potency_orders(self) -> None:
        cases = (
            ("THCA: 24.1%", 24.1, None, None),
            ("24.1% THCA", 24.1, None, None),
            ("Total THCA potency 28.4 percent", 28.4, None, None),
            ("Delta-9 THC: 0.28% and 25.2% THCA", 25.2, 0.28, None),
            ("Total THC: 22.7%", None, None, 22.7),
        )
        for description, thca, delta9, total in cases:
            with self.subTest(description=description):
                row = cloud_scan.record(
                    "fixture",
                    "Fixture",
                    HTML_ROUTE,
                    "Blue Dream THCA Flower 3.5g",
                    "https://example.test/products/blue-dream",
                    f"Sativa dominant hybrid. {description}",
                    35,
                    "in stock",
                )
                self.assertIsNotNone(row)
                self.assertEqual(row["description"], f"Sativa dominant hybrid. {description}")
                self.assertEqual(row["thca"], thca)
                self.assertEqual(row["delta9_thc"], delta9)
                self.assertEqual(row["direct_total_thc"], total)

    def test_shopify_tags_and_product_type_feed_lineage_and_potency(self) -> None:
        payload = json.dumps({
            "products": [{
                "id": 100,
                "handle": "blue-dream",
                "title": "Blue Dream THCA Flower",
                "body_html": "Indoor grown flower with 25.0% THCA.",
                "tags": ["Sativa Dominant Hybrid", "Indoor"],
                "product_type": "THCA Flower",
                "vendor": "Fixture",
                "images": [{"src": "https://example.test/blue.jpg"}],
                "variants": [{
                    "id": 101,
                    "title": "3.5g",
                    "price": "35.00",
                    "available": True,
                }],
            }]
        })
        rows = cloud_scan.shopify(payload, "fixture", "Fixture", SHOPIFY_ROUTE)
        self.assertEqual(len(rows), 1)
        self.assertIn("Sativa Dominant Hybrid", rows[0]["description"])
        self.assertEqual(rows[0]["thca"], 25.0)

        result = build_catalog(rows, generated_at="2026-07-22T00:00:00Z", detail_shards=1)
        index = json.loads(result.files["catalog-v4/index.json"])
        product = index["products"][0]
        self.assertEqual(product["lineage"], "sativa_leaning_hybrid")
        self.assertEqual(product["total_thc_display_percent"], 22)

    def test_woocommerce_preserves_atomic_rating_pair_and_attribute_potency(self) -> None:
        payload = json.dumps([{
            "id": 42,
            "name": "Gelato THCA Flower 3.5g",
            "permalink": "https://example.test/product/gelato/",
            "type": "simple",
            "has_options": False,
            "short_description": "Balanced hybrid loose flower.",
            "description": "Premium flower.",
            "categories": [{"name": "THCA Flower"}],
            "tags": [{"name": "Hybrid"}],
            "attributes": [{"name": "THCA", "terms": ["27.3%"]}],
            "average_rating": "4.8",
            "review_count": 126,
            "prices": {"currency_minor_unit": 2, "price": "3999"},
            "stock_status": "instock",
            "images": [{"src": "https://example.test/gelato.jpg"}],
        }])
        rows, diagnostics = cloud_scan.woo(payload, "fixture", "Fixture", WOO_ROUTE)
        self.assertEqual(diagnostics["variable_parents"], 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["thca"], 27.3)
        self.assertEqual(rows[0]["rating"], 4.8)
        self.assertEqual(rows[0]["review_count"], 126)

        result = build_catalog(rows, generated_at="2026-07-22T00:00:00Z", detail_shards=1)
        index = json.loads(result.files["catalog-v4/index.json"])
        product = index["products"][0]
        self.assertEqual(product["lineage"], "hybrid")
        self.assertEqual(product["rating"], 4.8)
        self.assertEqual(product["review_count"], 126)
        self.assertEqual(product["total_thc_display_percent"], 24)

    def test_jsonld_aggregate_rating_and_additional_property_are_preserved(self) -> None:
        payload = "<script type='application/ld+json'>" + json.dumps({
            "@type": "Product",
            "@id": "purple-milk",
            "sku": "purple-milk",
            "name": "Purple Milk THCA Flower 28g",
            "description": "Indica leaning hybrid flower.",
            "url": "https://example.test/products/purple-milk",
            "image": "https://example.test/purple.jpg",
            "aggregateRating": {"ratingValue": "4.6", "reviewCount": "84"},
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "THCA", "value": "26.5%"},
            ],
            "offers": {
                "@type": "Offer",
                "url": "https://example.test/products/purple-milk",
                "price": "90",
                "availability": "https://schema.org/InStock",
            },
        }) + "</script>"
        rows = cloud_scan.html_products(payload, "fixture", "Fixture", HTML_ROUTE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["thca"], 26.5)
        self.assertEqual(rows[0]["rating"], 4.6)
        self.assertEqual(rows[0]["review_count"], 84)

    def test_direct_source_total_thc_is_displayed_without_recalculation(self) -> None:
        row = cloud_scan.record(
            "fixture",
            "Fixture",
            HTML_ROUTE,
            "Orange Cookies THCA Flower 28g",
            "https://example.test/products/orange-cookies",
            "Hybrid. Total THC: 23.4%",
            90,
            "in stock",
        )
        result = build_catalog([row], generated_at="2026-07-22T00:00:00Z", detail_shards=1)
        index = json.loads(result.files["catalog-v4/index.json"])
        details = json.loads(result.files["catalog-v4/details/000.json"])
        self.assertEqual(index["products"][0]["total_thc_display_percent"], 23)
        self.assertEqual(details["products"][0]["total_thc"]["method"], "direct_source_total_thc")
        self.assertEqual(details["products"][0]["total_thc"]["direct_source_total_thc_percent"], 23.4)


    def test_multi_product_runtime_preserves_parser_metadata_arguments(self) -> None:
        original = {
            "record": cloud_scan.record,
            "product_links": cloud_scan.product_links,
            "HARD_EXCLUDE": cloud_scan.HARD_EXCLUDE,
            "SOURCES": cloud_scan.SOURCES,
        }
        worker = SimpleNamespace(
            core=cloud_scan,
            FALLBACK_EXCLUDE=cloud_scan.HARD_EXCLUDE,
            PRODUCT_PATHS=("/product/", "/products/"),
            FALLBACK_HTML_ROUTES={},
            path_text=lambda target: urlsplit(target).path.replace("-", " "),
        )
        reliability = SimpleNamespace(worker=worker)
        try:
            install_multi_product_runtime(reliability)
            payload = json.dumps({
                "products": [{
                    "id": 100,
                    "handle": "runtime-flower",
                    "title": "Runtime THCA Flower",
                    "body_html": "Sativa hybrid with Total THC: 21.8%",
                    "average_rating": "4.7",
                    "review_count": 33,
                    "variants": [{
                        "id": 101,
                        "title": "3.5g",
                        "price": "35.00",
                        "available": True,
                    }],
                }]
            })
            rows = cloud_scan.shopify(payload, "fixture", "Fixture", SHOPIFY_ROUTE)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["description"], "Sativa hybrid with Total THC: 21.8%")
            self.assertEqual(rows[0]["direct_total_thc"], 21.8)
            self.assertEqual(rows[0]["rating"], 4.7)
            self.assertEqual(rows[0]["review_count"], 33)
        finally:
            cloud_scan.record = original["record"]
            cloud_scan.product_links = original["product_links"]
            cloud_scan.HARD_EXCLUDE = original["HARD_EXCLUDE"]
            cloud_scan.SOURCES = original["SOURCES"]
            if hasattr(worker, "_multi_product_runtime_installed"):
                delattr(worker, "_multi_product_runtime_installed")

    def test_manifest_reports_metadata_coverage_instead_of_implying_completeness(self) -> None:
        populated = cloud_scan.record(
            "fixture",
            "Fixture",
            HTML_ROUTE,
            "Blue Dream THCA Flower 3.5g",
            "https://example.test/products/blue-dream",
            "Sativa. THCA: 24%",
            35,
            "in stock",
            "https://example.test/blue.jpg",
            rating=4.5,
            review_count=20,
        )
        blank = cloud_scan.record(
            "fixture",
            "Fixture",
            HTML_ROUTE,
            "Mystery THCA Flower 7g",
            "https://example.test/products/mystery",
            "Loose flower.",
            50,
            "in stock",
        )
        result = build_catalog([populated, blank], generated_at="2026-07-22T00:00:00Z", detail_shards=1)
        coverage = result.manifest["metadata_coverage"]
        self.assertEqual(coverage["product_count"], 2)
        self.assertEqual(coverage["fields"]["lineage"], {"populated": 1, "missing": 1, "coverage": 0.5})
        self.assertEqual(coverage["fields"]["total_thc"], {"populated": 1, "missing": 1, "coverage": 0.5})
        self.assertEqual(coverage["fields"]["rating"], {"populated": 1, "missing": 1, "coverage": 0.5})


if __name__ == "__main__":
    unittest.main()
