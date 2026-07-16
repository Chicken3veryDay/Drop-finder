from __future__ import annotations

import unittest

from scripts.cloud_scan import grams, weight


class CloudScanWeightEvidenceTests(unittest.TestCase):
    def test_incidental_numbers_are_not_weights(self) -> None:
        for label in ("Tier 1", "Type 1", "Tier 2", "4 pack", "THCA 24.1%", "THCA 18.2%", "THCA 22.4%"):
            with self.subTest(label=label):
                self.assertIsNone(grams(label))

    def test_pound_context_is_not_misread_as_ounces(self) -> None:
        for label in ("Quarter Pound", "quarter lb", "1/4 lb", "half pound", "1/2 lb"):
            with self.subTest(label=label):
                self.assertIsNone(grams(label))

    def test_explicit_and_supported_legacy_labels_remain_supported(self) -> None:
        expected = {
            "1 oz": 28.349,
            "2 ounces": 56.699,
            "4 oz": 113.398,
            "1/8": 3.544,
            "Quarter": 7.0874,
            "3.5g": 3.5,
        }
        for label, expected_grams in expected.items():
            with self.subTest(label=label):
                parsed, source_label = weight(label)
                self.assertEqual(parsed, expected_grams)
                self.assertTrue(source_label)


if __name__ == "__main__":
    unittest.main()
