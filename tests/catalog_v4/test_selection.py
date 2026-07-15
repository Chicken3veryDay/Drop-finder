from __future__ import annotations

import unittest

from scripts.catalog_v4.selection import select_active_variant


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.variants = [
            {"variant_id": "z", "grams": 3.5, "current_price": 21, "price_per_gram": 6, "in_stock": True},
            {"variant_id": "b", "grams": 7, "current_price": 35, "price_per_gram": 5, "in_stock": True},
            {"variant_id": "a", "grams": 14, "current_price": 70, "price_per_gram": 5, "in_stock": True},
            {"variant_id": "sold", "grams": 28, "current_price": 56, "price_per_gram": 2, "in_stock": False},
        ]

    def test_lowest_ppg_then_price_weight_id(self) -> None:
        self.assertEqual(select_active_variant(self.variants)["variant_id"], "b")
        tied = [
            {"variant_id": "b", "grams": 7, "current_price": 35, "price_per_gram": 5, "in_stock": True},
            {"variant_id": "a", "grams": 7, "current_price": 35, "price_per_gram": 5, "in_stock": True},
        ]
        self.assertEqual(select_active_variant(tied)["variant_id"], "a")

    def test_weight_bounds(self) -> None:
        self.assertEqual(select_active_variant(self.variants, minimum_grams=10)["variant_id"], "a")
        self.assertEqual(select_active_variant(self.variants, maximum_grams=4)["variant_id"], "z")
        self.assertIsNone(select_active_variant(self.variants, minimum_grams=30))


if __name__ == "__main__":
    unittest.main()
