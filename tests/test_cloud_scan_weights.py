from __future__ import annotations

import unittest

from scripts.cloud_scan import grams, record, weight


class CloudScanWeightTests(unittest.TestCase):
    def test_unrelated_numbers_are_not_package_weights(self) -> None:
        for value in (
            "Tier 1",
            "Type 1",
            "Tier 2",
            "4 pack",
            "THCA 24.1%",
            "THCA 18.2%",
            "THCA 22.4%",
        ):
            with self.subTest(value=value):
                self.assertIsNone(grams(value))

    def test_explicit_supported_weights_remain_parseable(self) -> None:
        cases = {
            "3.5g": 3.5,
            "1/8th": 3.544,
            "1 oz": 28.349,
            "2 ounces": 56.699,
            "4 oz": 113.398,
            "Quarter Pound": 112.0,
            "1/4 lb": 112.0,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(grams(value), expected)

    def test_explicit_weight_wins_over_decimal_potency(self) -> None:
        self.assertEqual(weight("THCA 24.1% flower, available in 3.5g"), (3.5, "3.5g"))

    def test_records_publish_weight_provenance_only_for_explicit_evidence(self) -> None:
        route = ("html", "https://vendor.example/thca-flower", "thca_flower")
        contaminated = record(
            "vendor",
            "Vendor",
            route,
            "Blue Dream THCA Flower Tier 1",
            "https://vendor.example/products/blue-dream",
            price=34.99,
            stock="in_stock",
        )
        self.assertIsNotNone(contaminated)
        self.assertIsNone(contaminated["grams"])
        self.assertIsNone(contaminated["price_per_gram"])
        self.assertEqual(contaminated["source_weight_label"], "")
        self.assertEqual(contaminated["weight_provenance"], "unavailable")

        explicit = record(
            "vendor",
            "Vendor",
            route,
            "Blue Dream THCA Flower 3.5g",
            "https://vendor.example/products/blue-dream-3-5g",
            price=35,
            stock="in_stock",
        )
        self.assertIsNotNone(explicit)
        self.assertEqual(explicit["grams"], 3.5)
        self.assertEqual(explicit["price_per_gram"], 10)
        self.assertEqual(explicit["source_weight_label"], "3.5g")
        self.assertEqual(explicit["weight_provenance"], "explicit_text")


if __name__ == "__main__":
    unittest.main()
