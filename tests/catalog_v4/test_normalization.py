from __future__ import annotations

import unittest
from decimal import Decimal

from scripts.catalog_v4.normalization import (
    canonical_strain_name,
    effects,
    environment,
    explicit_stock,
    lineage,
    normalize_weight,
    rating,
)


class NormalizationTests(unittest.TestCase):
    def test_weight_normalization(self) -> None:
        cases = {
            "3.5g": Decimal("3.5"),
            "1/8th oz": Decimal("3.5"),
            "Quarter oz": Decimal("7"),
            "half ounce": Decimal("14"),
            "one ounce": Decimal("28"),
            "two ounces": Decimal("56"),
            "1 Pound": Decimal("448"),
            "Quarter Pound": Decimal("112"),
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(normalize_weight(None, label)[0], expected)
        self.assertEqual(normalize_weight("7", "7 grams"), (Decimal("7"), "7 grams"))
        self.assertEqual(normalize_weight("28.3495", "Bulk flower 1 oz"), (Decimal("28"), "1 oz"))
        self.assertEqual(normalize_weight("448", "Bulk flower 1 Pound"), (Decimal("448"), "1 Pound"))
        self.assertIsNone(normalize_weight("7")[0])
        self.assertIsNone(normalize_weight(None, "family pack")[0])
        self.assertIsNone(normalize_weight(-1, "-1g")[0])

    def test_numeric_weight_requires_matching_text_evidence(self) -> None:
        for value, label in (
            ("28.3495", None),
            ("28.3495", "28.3495"),
            ("28.3495", "Tier 1"),
            ("28.3495", "THCA 24.1%"),
            ("56.699", "4 pack"),
            ("28.3495", "Quarter oz"),
        ):
            with self.subTest(value=value, label=label):
                self.assertIsNone(normalize_weight(value, label)[0])

    def test_canonical_strain_name_is_conservative(self) -> None:
        self.assertEqual(
            canonical_strain_name("Blue Dream THCA Flower | 3.5g", "3.5g"),
            "Blue Dream",
        )
        self.assertEqual(canonical_strain_name("Hash Burger THCA Flower"), "Hash Burger")
        self.assertEqual(canonical_strain_name("Premium OG - Limited Drop"), "Premium OG")
        cases = {
            "ADL | THCa Flower | Tier 1": "ADL",
            "Fidel Runtz | THCa Flower | Tier 1": "Fidel Runtz",
            "Candy Runtz THCa Flower Smalls": "Candy Runtz",
            "Cherry Bordeaux THCa Flower Smalls": "Cherry Bordeaux",
            "Canal St. Runtz Premium": "Canal St. Runtz",
            "Cherry Cookies Greenhouse": "Cherry Cookies",
            "Blue Nerdz THCa": "Blue Nerdz",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(canonical_strain_name(source), expected)
        for legitimate in ("Premium OG", "Greenhouse Effect", "Flower Power", "Tier One"):
            with self.subTest(legitimate=legitimate):
                self.assertEqual(canonical_strain_name(legitimate), legitimate)

    def test_all_six_lineages(self) -> None:
        expected = {
            "Indica": "indica",
            "Indica-leaning hybrid": "indica_leaning_hybrid",
            "Hybrid": "hybrid",
            "Sativa-leaning hybrid": "sativa_leaning_hybrid",
            "Sativa": "sativa",
            "Unknown": "unknown",
        }
        for source, expected_value in expected.items():
            with self.subTest(source=source):
                self.assertEqual(lineage(source)[0], expected_value)
        self.assertEqual(lineage(None, "A sativa dominant cultivar")[0], "sativa_leaning_hybrid")
        self.assertEqual(lineage(None, "Relaxing evening flower")[0], "unknown")

    def test_effect_environment_rating_do_not_fabricate(self) -> None:
        self.assertEqual(effects("Calm, Creative, calm")[0], ["Calm", "Creative"])
        self.assertEqual(effects(None)[0], [])
        self.assertEqual(environment("mixed light")[0], "greenhouse")
        self.assertEqual(environment(None, "sun-grown buds")[0], "outdoor")
        self.assertEqual(rating(4.7, 182)[:2], (4.7, 182))
        self.assertEqual(rating(4.7, None)[:2], (None, None))
        self.assertEqual(rating(6, 20)[:2], (None, None))

    def test_stock_requires_explicit_source_state(self) -> None:
        self.assertEqual(explicit_stock(True)[0], True)
        self.assertEqual(explicit_stock("in_stock")[0], True)
        self.assertEqual(explicit_stock("sold out")[0], False)
        self.assertIsNone(explicit_stock("ships soon")[0])
        self.assertIsNone(explicit_stock(None)[0])


if __name__ == "__main__":
    unittest.main()
