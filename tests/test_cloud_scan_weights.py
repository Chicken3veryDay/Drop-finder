from __future__ import annotations

import unittest

from scripts.cloud_scan import grams


class CloudScanWeightTests(unittest.TestCase):
    def test_explicit_weights_are_preserved(self) -> None:
        cases = {
            "0.5g": 0.5,
            "3.5 grams": 3.5,
            "1/8th ounce": 3.544,
            "1/8 oz": 3.544,
            "quarter oz": 7.0874,
            "1 oz": 28.349,
            "2 ounces": 56.699,
            "4 oz": 113.398,
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(grams(label), expected)

    def test_unrelated_numbers_and_pounds_are_not_weight_evidence(self) -> None:
        labels = (
            "Tier 1",
            "Type 1",
            "Tier 2",
            "4 pack",
            "THCA 24.1%",
            "THCA 18.2%",
            "THCA 22.4%",
            "Quarter Pound",
            "quarter lb",
            "1/4 lb",
        )
        for label in labels:
            with self.subTest(label=label):
                self.assertIsNone(grams(label))

    def test_explicit_weight_wins_over_potency_text(self) -> None:
        self.assertEqual(grams("Blue Dream THCA 24.1% 3.5g"), 3.5)


if __name__ == "__main__":
    unittest.main()
