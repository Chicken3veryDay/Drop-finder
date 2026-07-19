import math
import unittest

from scripts.multi_product.classification import CANNABIS_VAPE, PSILOCYBIN_VAPE
from scripts.multi_product.normalization import comparison_price, quantity_fields
from scripts.multi_product.publication import reject_reason


class VapeQuantityIntegrityTests(unittest.TestCase):
    def product(self, primary_type=CANNABIS_VAPE, **values):
        evidence = {
            "primary_type": primary_type,
            "type_tags": (primary_type,),
            "explicit_cannabis": primary_type == CANNABIS_VAPE,
            "explicit_psilocybin": primary_type == PSILOCYBIN_VAPE,
            "explicit_vape": True,
            "amanita_signal": False,
        }
        return {
            "id": "vape",
            "product_id": "vape",
            "source_id": "fixture",
            "vendor": "Fixture",
            "name": "Fixture Vape",
            "url": "https://example.test/vape",
            "primary_type": primary_type,
            "type_tags": (primary_type,),
            "classification_evidence": evidence,
            "price": 20.0,
            "availability": "in_stock",
            **values,
        }

    def test_mass_only_vape_preserves_evidence_and_is_rejected(self):
        quantity = quantity_fields("Disposable vape 2g", CANNABIS_VAPE)
        self.assertEqual(quantity["grams"], 2.0)
        self.assertIsNone(quantity["volume_ml"])
        self.assertEqual(quantity["quantity_value"], 2.0)
        self.assertEqual(quantity["quantity_unit"], "g")
        comparison = comparison_price(40, quantity)
        product = self.product(price=40, **quantity, **comparison)
        self.assertEqual(reject_reason(product), "unsupported_vape_mass_quantity")

    def test_explicit_volume_wins_when_both_units_are_present(self):
        quantity = quantity_fields("Disposable vape 2g / 1mL", CANNABIS_VAPE)
        self.assertIsNone(quantity["grams"])
        self.assertEqual(quantity["volume_ml"], 1.0)
        self.assertEqual(quantity["quantity_value"], 1.0)
        self.assertEqual(quantity["quantity_unit"], "ml")

    def test_coherent_volume_quantity_is_publishable_for_both_vape_types(self):
        for primary_type in (CANNABIS_VAPE, PSILOCYBIN_VAPE):
            with self.subTest(primary_type=primary_type):
                product = self.product(
                    primary_type,
                    grams=None,
                    volume_ml=1.0,
                    quantity_value=1.0,
                    quantity_unit="ml",
                    comparison_metric="price_per_ml",
                    comparison_price=20.0,
                    price_per_ml=20.0,
                )
                self.assertIsNone(reject_reason(product))

    def test_missing_or_inconsistent_volume_comparison_is_rejected(self):
        base = dict(grams=None, volume_ml=1.0, quantity_value=1.0, quantity_unit="ml")
        self.assertEqual(
            reject_reason(self.product(**base, comparison_metric=None, comparison_price=None)),
            "missing_vape_comparison_price",
        )
        self.assertEqual(
            reject_reason(self.product(
                **base,
                comparison_metric="price_per_ml",
                comparison_price=19,
                price_per_ml=20,
            )),
            "inconsistent_vape_comparison_price",
        )
        self.assertEqual(
            reject_reason(self.product(grams=None, volume_ml=None, quantity_value=None, quantity_unit=None)),
            "missing_vape_volume",
        )

    def test_quantity_value_must_match_explicit_volume(self):
        self.assertEqual(
            reject_reason(self.product(
                grams=None,
                volume_ml=1.0,
                quantity_value=2.0,
                quantity_unit="ml",
                comparison_metric="price_per_ml",
                comparison_price=20.0,
                price_per_ml=20.0,
            )),
            "inconsistent_vape_quantity",
        )

    def test_non_finite_values_do_not_satisfy_quantity_contract(self):
        product = self.product(
            grams=None,
            volume_ml=math.inf,
            quantity_value=math.inf,
            quantity_unit="ml",
            comparison_metric="price_per_ml",
            comparison_price=20,
            price_per_ml=20,
        )
        self.assertEqual(reject_reason(product), "missing_vape_volume")


if __name__ == "__main__":
    unittest.main()
