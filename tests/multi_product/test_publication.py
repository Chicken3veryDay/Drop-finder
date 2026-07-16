from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.multi_product import CANNABIS_VAPE, PSILOCYBIN_MUSHROOM
from scripts.multi_product.publication import reject_reason, self_test


class PublicationTests(unittest.TestCase):
    def test_type_aware_sanitizer_and_controlled_link_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(self_test(root), 0)
            catalog = json.loads((root / "out" / "catalog.json").read_text(encoding="utf-8"))
            controlled = [
                product
                for product in catalog["products"]
                if product["primary_type"] == PSILOCYBIN_MUSHROOM
            ]
            self.assertEqual(len(controlled), 1)
            self.assertEqual(controlled[0]["url"], "")
            self.assertIsNone(controlled[0]["public_purchase_url"])
            self.assertEqual(catalog["products_by_type"]["cannabis_vape"], 1)

    def test_vape_publication_rejects_mass_without_erasing_it(self) -> None:
        product = {
            "id": "mass-vape",
            "source_id": "vendor",
            "vendor": "Vendor",
            "primary_type": CANNABIS_VAPE,
            "type_tags": [CANNABIS_VAPE],
            "name": "THCA Live Resin Disposable Vape 2g",
            "url": "https://example.test/products/vape",
            "price": 40,
            "availability": "in_stock",
            "grams": 2,
            "volume_ml": None,
            "quantity_unit": "g",
            "comparison_metric": "price_per_gram",
            "comparison_price": 20,
            "price_per_gram": 20,
            "classification_evidence": {
                "primary_type": CANNABIS_VAPE,
                "type_tags": [CANNABIS_VAPE],
                "explicit_cannabis": True,
                "explicit_vape": True,
            },
        }
        self.assertEqual(reject_reason(product), "unsupported_vape_mass_quantity")

        product.update({
            "grams": None,
            "volume_ml": 1,
            "quantity_unit": "ml",
            "comparison_metric": "price_per_ml",
            "comparison_price": 40,
            "price_per_gram": None,
            "price_per_ml": 40,
        })
        self.assertIsNone(reject_reason(product))


if __name__ == "__main__":
    unittest.main()
