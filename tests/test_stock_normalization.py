from __future__ import annotations

import unittest

from scripts.catalog_v4 import build_catalog
from scripts.catalog_v4.normalization import explicit_stock
from scripts.cloud_scan import availability, record


NEGATIVE_STATES = (
    "unavailable",
    "currently unavailable",
    "unavailable for order",
    "not available",
    "not yet available",
    "not in stock",
    "not currently in stock",
    "out_of_stock",
    "sold out",
)

POSITIVE_STATES = (
    "available",
    "currently available",
    "available for order",
    "in_stock",
    "instock",
)


class StockNormalizationTests(unittest.TestCase):
    def test_legacy_scanner_checks_negative_states_before_positive_tokens(self) -> None:
        for value in NEGATIVE_STATES:
            with self.subTest(value=value):
                self.assertEqual(availability(value), "out_of_stock")
        for value in POSITIVE_STATES:
            with self.subTest(value=value):
                self.assertEqual(availability(value), "in_stock")
        self.assertEqual(availability(True), "in_stock")
        self.assertEqual(availability(False), "out_of_stock")
        self.assertEqual(availability("availability pending"), "unknown")

    def test_legacy_record_preserves_raw_stock_evidence(self) -> None:
        row = record(
            "vendor",
            "Vendor",
            ("html", "https://vendor.example/thca-flower", "thca_flower"),
            "Blue Dream THCA Flower 3.5g",
            "https://vendor.example/products/blue-dream",
            price=25,
            stock="currently unavailable",
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["availability"], "out_of_stock")
        self.assertEqual(row["availability_raw"], "currently unavailable")
        self.assertEqual(row["availability_normalization"], "explicit_source_state")

    def test_catalog_normalizer_rejects_negated_positive_phrases(self) -> None:
        for value in NEGATIVE_STATES:
            with self.subTest(value=value):
                self.assertEqual(explicit_stock(value), (False, "explicit_source_state"))
        for value in POSITIVE_STATES:
            with self.subTest(value=value):
                self.assertEqual(explicit_stock(value), (True, "explicit_source_state"))
        self.assertEqual(explicit_stock(True), (True, "explicit_boolean"))
        self.assertEqual(explicit_stock(False), (False, "explicit_boolean"))
        self.assertEqual(explicit_stock("availability pending"), (None, "unknown"))

    def test_catalog_rejects_legacy_negative_stock_row(self) -> None:
        row = record(
            "vendor",
            "Vendor",
            ("html", "https://vendor.example/thca-flower", "thca_flower"),
            "Blue Dream THCA Flower 3.5g",
            "https://vendor.example/products/blue-dream",
            price=25,
            stock="currently unavailable",
        )

        result = build_catalog([row], generated_at="2026-01-01T00:00:00Z", detail_shards=1)

        self.assertEqual(result.product_count, 0)
        self.assertEqual(result.variant_count, 0)
        self.assertEqual(result.rejections["reason_counts"], {"out_of_stock_variant": 1})


if __name__ == "__main__":
    unittest.main()
