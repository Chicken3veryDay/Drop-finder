from __future__ import annotations

import unittest

from scripts.multi_product import (
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    PSILOCYBIN_MUSHROOM,
    PSILOCYBIN_VAPE,
    classify_product,
    comparison_price,
    completeness_score,
    quantity_fields,
    type_specific_fields,
    validates_classification,
)


class ClassificationTests(unittest.TestCase):
    def test_strict_thca_flower_stays_flower(self) -> None:
        result = classify_product(name="Blue Dream THCA Flower 3.5g")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_type, CANNABIS_FLOWER)
        self.assertTrue(validates_classification(result))
        self.assertTrue(result.permits_public_purchase_link)

    def test_preroll_does_not_contaminate_flower(self) -> None:
        self.assertIsNone(classify_product(name="Blue Dream THCA Flower Pre-Rolls"))

    def test_cannabis_vape_requires_cannabis_evidence(self) -> None:
        result = classify_product(name="THCA Live Resin Disposable Vape 1mL")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_type, CANNABIS_VAPE)
        self.assertTrue(validates_classification(result))
        self.assertIsNone(classify_product(name="Empty 510 Vape Cartridge"))

    def test_psilocybin_mushroom_is_informational_only(self) -> None:
        result = classify_product(name="Psilocybe Cubensis Psilocybin Mushrooms 7g")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_type, PSILOCYBIN_MUSHROOM)
        self.assertFalse(result.permits_public_purchase_link)
        self.assertTrue(validates_classification(result))

    def test_psilocybin_vape_is_specific_and_informational_only(self) -> None:
        result = classify_product(name="Psilocybin Disposable Vape 1mL 2%")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_type, PSILOCYBIN_VAPE)
        self.assertFalse(result.permits_public_purchase_link)

    def test_amanita_is_not_mislabeled_as_psilocybin(self) -> None:
        self.assertIsNone(classify_product(name="Amanita Muscaria Mushroom Caps 7g"))
        self.assertIsNone(classify_product(name="Amanita Muscimol Disposable Vape 1mL"))

    def test_mixed_tags_are_preserved(self) -> None:
        result = classify_product(name="THCA + Psilocybin Mushroom Disposable Vape 1mL")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.primary_type, PSILOCYBIN_VAPE)
        self.assertIn(CANNABIS_VAPE, result.type_tags)
        self.assertIn(PSILOCYBIN_VAPE, result.type_tags)

    def test_quantity_and_comparison_metrics_are_type_aware(self) -> None:
        flower_quantity = quantity_fields("3.5g jar", CANNABIS_FLOWER)
        self.assertEqual(flower_quantity["grams"], 3.5)
        self.assertEqual(comparison_price("35", flower_quantity)["price_per_gram"], 10.0)
        vape_quantity = quantity_fields("1mL disposable", CANNABIS_VAPE)
        self.assertEqual(vape_quantity["volume_ml"], 1.0)
        self.assertEqual(comparison_price("25", vape_quantity)["price_per_ml"], 25.0)

    def test_type_specific_fields_do_not_guess(self) -> None:
        fields = type_specific_fields(
            "Psilocybe cubensis disposable 1mL, psilocybin 2.5%, 800 puffs",
            PSILOCYBIN_VAPE,
        )
        self.assertEqual(fields["species"], "Psilocybe Cubensis")
        self.assertEqual(fields["psilocybin_percent"], 2.5)
        self.assertEqual(fields["puff_count"], 800)
        self.assertEqual(fields["device_type"], "disposable")

    def test_completeness_score_is_bounded(self) -> None:
        score = completeness_score({
            "primary_type": CANNABIS_VAPE,
            "name": "Vape",
            "vendor": "Vendor",
            "price": 20,
            "availability": "in_stock",
            "volume_ml": 1,
            "device_type": "disposable",
            "price_per_ml": 20,
            "classification_evidence": {"primary_type": CANNABIS_VAPE},
        })
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
